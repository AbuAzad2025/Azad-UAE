from app.factory import create_app
from utils.exceptions import PaymentRequired

app = create_app()
app.config["TESTING"] = True
app.config["DEBUG"] = False


@app.route("/trigger-402")
def trigger_402():
    raise PaymentRequired("Test 402")


with app.test_client() as client:
    response = client.get("/trigger-402")
    print(f"Status: {response.status_code}")
    print(f"Data contains 402: {b'402' in response.data}")
    print(f"Data contains Payment Required: {b'Payment Required' in response.data}")
