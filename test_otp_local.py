import asyncio
import httpx

async def run_test():
    # Make sure your backend is running on localhost:8000
    # Command: uvicorn app.main:app --reload
    
    BASE_URL = "http://localhost:8000/api/v1/auth"
    email = "test.otp.user@tailor24.dev"

    async with httpx.AsyncClient() as client:
        print(f"--- 1. Sending OTP to {email} ---")
        res1 = await client.post(f"{BASE_URL}/send-otp", json={"email": email})
        print(f"Status: {res1.status_code}")
        print(f"Response: {res1.json()}\n")
        
        # Check your terminal running uvicorn for the mocked OTP!
        otp = input("Enter the 6-digit OTP printed in the uvicorn terminal: ")
        
        print("\n--- 2. Registering User with OTP ---")
        reg_payload = {
            "email": email,
            "otp": otp,
            "name": "Local Test User",
            "phone": "+919999988888",
            "role": "CUSTOMER"
        }
        res2 = await client.post(f"{BASE_URL}/verify-otp-register", json=reg_payload)
        print(f"Status: {res2.status_code}")
        print(f"Response: {res2.json()}\n")
        
        if res2.status_code == 200:
            print("Successfully registered and got JWT!")
            print("Access Token Snippet:", res2.json()["data"]["access_token"][:30], "...")

if __name__ == "__main__":
    asyncio.run(run_test())
