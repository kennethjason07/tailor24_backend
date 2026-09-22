"""
Tests for Hub Manager Credential Management (Riders, Workers, Tailors, Activation, Reset Access, Audit Logging).
"""
import pytest
from bson import ObjectId
from tests.conftest import create_test_user, get_token, auth_headers


@pytest.fixture
def hub_setup(db):
    # Create Hub
    hub_res = db.hubs.insert_one({
        "name": "Bengaluru Hub #01",
        "code": "BLR-01",
        "address": "123 Indiranagar, Bengaluru",
        "city": "Bengaluru",
        "isActive": True,
    })
    hub_id = str(hub_res.inserted_id)

    # Create Manager
    manager = create_test_user(db, "Manager Blr", "+919000000001", "HUB_MANAGER")
    db.users.update_one({"_id": manager["_id"]}, {"$set": {"hubId": hub_id}})

    # Create Manager from Hub 2
    hub2_res = db.hubs.insert_one({"name": "Mysuru Hub #01", "code": "MYS-01", "isActive": True})
    hub2_id = str(hub2_res.inserted_id)
    manager2 = create_test_user(db, "Manager Mysuru", "+919000000002", "HUB_MANAGER")
    db.users.update_one({"_id": manager2["_id"]}, {"$set": {"hubId": hub2_id}})

    return {
        "hub_id": hub_id,
        "manager": manager,
        "hub2_id": hub2_id,
        "manager2": manager2,
    }


def test_hub_manager_create_rider(client, db, hub_setup):
    token = get_token(client, "+919000000001")
    headers = auth_headers(token)

    # 1. Create Rider without password (PENDING_ACTIVATION)
    res = client.post(
        "/api/v1/manager/riders",
        json={"name": "Ravi Kumar", "phone": "+919876543210", "email": "ravi@example.com"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["name"] == "Ravi Kumar"
    assert data["role"] == "RIDER"
    assert data["accountStatus"] == "PENDING_ACTIVATION"
    assert data["hubId"] == hub_setup["hub_id"]
    assert "activationLink" in data
    activation_token = data["activationToken"]

    # 1b. Create Rider WITH Direct Password (ACTIVE)
    res_direct = client.post(
        "/api/v1/manager/riders",
        json={"name": "Suresh Rider", "phone": "+919876543999", "password": "DirectRiderPassword123"},
        headers=headers,
    )
    assert res_direct.status_code == 200, res_direct.text
    direct_data = res_direct.json()["data"]
    assert direct_data["accountStatus"] == "ACTIVE"

    # Test direct rider login immediately
    direct_login = client.post("/api/v1/auth/login", json={"phone": "+919876543999", "password": "DirectRiderPassword123"})
    assert direct_login.status_code == 200


    # 2. List Riders
    list_res = client.get("/api/v1/manager/riders", headers=headers)
    assert list_res.status_code == 200
    riders = list_res.json()["data"]
    assert len(riders) >= 1
    assert any(r["name"] == "Ravi Kumar" for r in riders)

    # 3. Duplicate Phone Prevention
    dup_res = client.post(
        "/api/v1/manager/riders",
        json={"name": "Duplicate Rider", "phone": "+919876543210"},
        headers=headers,
    )
    assert dup_res.status_code == 409

    # 4. Activate Account via Public Endpoint
    act_res = client.post(
        "/api/v1/auth/activate",
        json={"activationToken": activation_token, "password": "NewRiderPassword123"},
    )
    assert act_res.status_code == 200
    assert act_res.json()["data"]["accountStatus"] == "ACTIVE"

    # 5. Verify Login with set password
    login_res = client.post("/api/v1/auth/login", json={"phone": "+919876543210", "password": "NewRiderPassword123"})
    assert login_res.status_code == 200

    # 6. Verify audit log created
    audit = db.audit_logs.find_one({"targetUserId": data["userId"], "action": "USER_CREATED"})
    assert audit is not None
    assert audit["targetRole"] == "RIDER"


def test_hub_manager_create_worker(client, db, hub_setup):
    token = get_token(client, "+919000000001")
    headers = auth_headers(token)

    res = client.post(
        "/api/v1/manager/workers",
        json={"name": "Anita Staff", "phone": "+919876543211", "role": "HUB_STAFF"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["role"] == "HUB_STAFF"
    assert data["hubId"] == hub_setup["hub_id"]

    # Attempt forbidden role
    forbidden_res = client.post(
        "/api/v1/manager/workers",
        json={"name": "Bad Worker", "phone": "+919876543212", "role": "SUPER_ADMIN"},
        headers=headers,
    )
    assert forbidden_res.status_code in [400, 403]


def test_hub_manager_tailor_application_flow(client, db, hub_setup):
    token = get_token(client, "+919000000001")
    headers = auth_headers(token)

    # 1. Create Approved Tailor Application
    app_res = db.tailor_applications.insert_one({
        "applicantName": "Lata Tailor",
        "phone": "+919876543213",
        "skills": ["Kurti", "Blouse"],
        "genderSpecialization": ["LADIES"],
        "capacity": 30,
        "status": "APPROVED",
        "hubId": hub_setup["hub_id"],
    })
    app_id = str(app_res.inserted_id)

    # 2. Create Tailor Account from Approved Application
    create_res = client.post(f"/api/v1/manager/tailors/{app_id}/create-account", headers=headers)
    assert create_res.status_code == 200, create_res.text
    tailor_data = create_res.json()["data"]
    assert tailor_data["role"] == "TAILOR"
    assert tailor_data["skills"] == ["Kurti", "Blouse"]

    # 2b. Create Tailor Account with Direct Password
    app2_res = db.tailor_applications.insert_one({
        "applicantName": "Geeta Tailor",
        "phone": "+919876543888",
        "skills": ["Saree"],
        "status": "APPROVED",
        "hubId": hub_setup["hub_id"],
    })
    app2_id = str(app2_res.inserted_id)

    create_direct_res = client.post(
        f"/api/v1/manager/tailors/{app2_id}/create-account",
        json={"password": "TailorPassword123"},
        headers=headers,
    )
    assert create_direct_res.status_code == 200, create_direct_res.text
    assert create_direct_res.json()["data"]["accountStatus"] == "ACTIVE"

    # Test login for direct tailor
    tailor_login = client.post("/api/v1/auth/login", json={"phone": "+919876543888", "password": "TailorPassword123"})
    assert tailor_login.status_code == 200

    # 3. Verify Tailor Profile Created
    prof = db.tailor_profiles.find_one({"userId": tailor_data["userId"]})
    assert prof is not None
    assert prof["skills"] == ["Kurti", "Blouse"]



def test_hub_isolation_and_cross_management(client, db, hub_setup):
    # Manager 1 Token
    m1_token = get_token(client, "+919000000001")
    m1_headers = auth_headers(m1_token)

    # Manager 2 Token
    m2_token = get_token(client, "+919000000002")
    m2_headers = auth_headers(m2_token)

    # Create rider for Hub 1
    res1 = client.post(
        "/api/v1/manager/riders",
        json={"name": "Hub1 Rider", "phone": "+919876543214"},
        headers=m1_headers,
    )
    assert res1.status_code == 200
    rider1_id = res1.json()["data"]["userId"]

    # Manager 2 tries to view/deactivate Hub 1 rider
    view_res = client.get(f"/api/v1/manager/riders/{rider1_id}", headers=m2_headers)
    assert view_res.status_code == 403

    deact_res = client.post(f"/api/v1/manager/riders/{rider1_id}/deactivate", headers=m2_headers)
    assert deact_res.status_code == 403


def test_reset_access_and_deactivate(client, db, hub_setup):
    token = get_token(client, "+919000000001")
    headers = auth_headers(token)

    # Create Rider
    res = client.post(
        "/api/v1/manager/riders",
        json={"name": "Reset Rider", "phone": "+919876543215"},
        headers=headers,
    )
    rider_id = res.json()["data"]["userId"]

    # Reset Access
    reset_res = client.post(f"/api/v1/manager/riders/{rider_id}/reset-access", headers=headers)
    assert reset_res.status_code == 200
    assert "activationToken" in reset_res.json()["data"]

    # Deactivate Account
    deact_res = client.post(f"/api/v1/manager/riders/{rider_id}/deactivate", headers=headers)
    assert deact_res.status_code == 200
    assert deact_res.json()["data"]["isActive"] is False

    # Reactivate Account
    react_res = client.post(f"/api/v1/manager/riders/{rider_id}/reactivate", headers=headers)
    assert react_res.status_code == 200
    assert react_res.json()["data"]["isActive"] is True
