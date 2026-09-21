from unittest.mock import patch

def test_send_otp(client):
    with patch("app.modules.auth.service.send_otp_email") as mock_send_email:
        response = client.post(
            "/api/v1/auth/send-otp",
            json={"email": "testtailor@tailor24.dev"}
        )
        assert response.status_code == 200
        assert response.json()["message"] == "OTP sent to testtailor@tailor24.dev"
        mock_send_email.assert_called_once()
        
def test_verify_otp_register_and_login(client):
    with patch("app.modules.auth.service.send_otp_email") as mock_send_email:
        client.post(
            "/api/v1/auth/send-otp",
            json={"email": "newuser@tailor24.dev"}
        )
        
        args, kwargs = mock_send_email.call_args
        plain_otp = args[1]
        
        reg_payload = {
            "email": "newuser@tailor24.dev",
            "otp": plain_otp,
            "name": "New OTP Tailor",
            "phone": "+919999999999",
            "role": "TAILOR"
        }
        response = client.post("/api/v1/auth/verify-otp-register", json=reg_payload)
        assert response.status_code == 200
        data = response.json()["data"]
        assert "access_token" in data
        
        client.post(
            "/api/v1/auth/send-otp",
            json={"email": "newuser@tailor24.dev"}
        )
        args2, kwargs2 = mock_send_email.call_args
        plain_otp_login = args2[1]
        
        login_payload = {
            "email": "newuser@tailor24.dev",
            "otp": plain_otp_login
        }
        login_resp = client.post("/api/v1/auth/verify-otp-login", json=login_payload)
        assert login_resp.status_code == 200
        assert "access_token" in login_resp.json()["data"]

def test_verify_otp_invalid(client):
    login_payload = {
        "email": "doesntexist@tailor24.dev",
        "otp": "000000"
    }
    response = client.post("/api/v1/auth/verify-otp-login", json=login_payload)
    assert response.status_code == 401
    assert "Invalid or expired OTP" in response.json()["message"]
