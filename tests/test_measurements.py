import pytest
from bson import ObjectId
from app.common.enums import MeasurementStatus

@pytest.fixture
def auth_headers(create_test_user, client):
    user = create_test_user("cust1@test.com", "CUSTOMER")
    res = client.post("/api/v1/auth/login", json={"email": "cust1@test.com", "password": "password123"})
    token = res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def hub_ops_headers(create_test_user, client):
    user = create_test_user("hub1@test.com", "HUB_MANAGER")
    res = client.post("/api/v1/auth/login", json={"email": "hub1@test.com", "password": "password123"})
    token = res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_create_and_list_profiles(client, auth_headers):
    # Create profile
    payload = {
        "profileName": "My Size",
        "gender": "GENTS",
        "measurements": {
            "unit": "cm",
            "values": {"chest": 40},
            "custom": {}
        }
    }
    res = client.post("/api/v1/customers/measurement-profiles", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["profileName"] == "My Size"
    assert data["measurements"]["values"]["chest"] == 40
    
    # List profiles
    res = client.get("/api/v1/customers/measurement-profiles", headers=auth_headers)
    assert res.status_code == 200
    assert len(res.json()["data"]) >= 1

def test_order_creation_without_measurements(client, auth_headers, test_db):
    # Insert address and hub to avoid FK issues
    addr_id = str(ObjectId())
    hub_id = str(ObjectId())
    test_db.addresses.insert_one({"_id": ObjectId(addr_id), "customerId": ObjectId()})
    test_db.hubs.insert_one({"_id": ObjectId(hub_id), "code": "HUB-123"})

    # Option C: No measurements
    order_payload = {
        "addressId": addr_id,
        "hubId": hub_id,
        "pickupSlot": {"date": "2026-10-10", "startTime": "10:00", "endTime": "11:00"},
        "paymentMethod": "COD",
        "garments": [
            {
                "type": "SHIRT",
                "gender": "GENTS",
                "serviceCharge": 100.0,
                # no measurements
            }
        ]
    }
    res = client.post("/api/v1/orders", json=order_payload, headers=auth_headers)
    assert res.status_code == 200
    g = res.json()["data"]["garments"][0]
    
    assert g["measurements"]["status"] == MeasurementStatus.NOT_PROVIDED.value
    assert g["measurements"]["source"] is None
    
    g_id = g["_id"]
    
    # Try to move to cutting -> Should fail!
    # First INTAKE
    scan_res = client.post(f"/api/v1/garments/{g_id}/scan", json={"action": "INTAKE", "hubId": hub_id}, headers=auth_headers)
    # Customers can't INTAKE. Oops. Let's not test the whole flow here unless using hub_ops_headers.

def test_cutting_validation(client, auth_headers, hub_ops_headers, test_db):
    addr_id = str(ObjectId())
    hub_id = str(ObjectId())
    test_db.addresses.insert_one({"_id": ObjectId(addr_id), "customerId": ObjectId()})
    test_db.hubs.insert_one({"_id": ObjectId(hub_id), "code": "HUB-124"})

    # Order without measurements
    order_payload = {
        "addressId": addr_id,
        "hubId": hub_id,
        "pickupSlot": {"date": "2026-10-10", "startTime": "10:00", "endTime": "11:00"},
        "paymentMethod": "COD",
        "garments": [
            {
                "type": "SHIRT",
                "gender": "GENTS",
                "serviceCharge": 100.0,
            }
        ]
    }
    res = client.post("/api/v1/orders", json=order_payload, headers=auth_headers)
    g_id = res.json()["data"]["garments"][0]["_id"]
    
    # Hub INTAKE
    res = client.post(f"/api/v1/garments/{g_id}/scan", json={"action": "INTAKE", "hubId": hub_id}, headers=hub_ops_headers)
    assert res.status_code == 200
    
    # Try cutting
    res = client.post(f"/api/v1/garments/{g_id}/scan", json={"action": "CUTTING_STARTED", "hubId": hub_id}, headers=hub_ops_headers)
    assert res.status_code == 409
    assert "Measurements must be confirmed" in res.json()["message"]
    
    # Update and confirm measurements
    res = client.patch(f"/api/v1/garments/{g_id}/measurements", json={"unit": "cm", "values": {"chest": 40}, "custom": {}}, headers=auth_headers)
    assert res.status_code == 200
    
    res = client.post(f"/api/v1/garments/{g_id}/measurements/confirm", headers=auth_headers)
    assert res.status_code == 200
    
    # Now cutting should succeed
    res = client.post(f"/api/v1/garments/{g_id}/scan", json={"action": "CUTTING_STARTED", "hubId": hub_id}, headers=hub_ops_headers)
    assert res.status_code == 200
