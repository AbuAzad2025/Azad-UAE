from locust import HttpUser, task, between

class AzadUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        self.client.post("/auth/login", data={
            "username": "test_user",
            "password": "test_pass"
        })
    
    @task(3)
    def dashboard(self):
        self.client.get("/main/dashboard")
    
    @task(1)
    def products(self):
        self.client.get("/products/")
