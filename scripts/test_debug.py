"""Debug test to understand mock behavior."""

from unittest.mock import MagicMock

from app.factory import create_app
from services.logging_core import LoggingCore
from utils.exceptions import PaymentRequired

# Simulate what conftest does
original_log_error = LoggingCore.log_error
setattr(LoggingCore, "log_error", lambda *args, **kwargs: None)
print(f"After conftest patch: LoggingCore.log_error = {LoggingCore.log_error}")

# Now simulate what mocker.patch.object does
mock_log = MagicMock()
setattr(LoggingCore, "log_error", mock_log)
print(f"After mocker.patch.object: LoggingCore.log_error = {LoggingCore.log_error}")

# Create app and trigger handler
app = create_app()
app.config["TESTING"] = True
app.config["DEBUG"] = False


@app.route("/trigger-402")
def trigger_402():
    raise PaymentRequired("Test 402")


with app.test_client() as client:
    response = client.get("/trigger-402")
    print(f"Status: {response.status_code}")

print(f"Mock called: {mock_log.called}")
print(f"Mock call count: {mock_log.call_count}")
if mock_log.called:
    print(f"Mock call args: {mock_log.call_args}")

# Restore
setattr(LoggingCore, "log_error", original_log_error)
