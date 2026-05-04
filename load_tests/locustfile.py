import random

from locust import HttpUser, between, task

MODELS = ["text-small", "text-large", "image-small"]

TEXTS = [
    "this movie was absolutely fantastic",
    "terrible experience, would not recommend",
    "it was okay, nothing particularly special",
    "best product I have ever bought in my life",
    "complete waste of money and time",
    "I really enjoyed every single minute of it",
    "not what I expected but pleasantly surprised",
]


class InferenceUser(HttpUser):
    wait_time = between(0.05, 0.3)

    @task(4)
    def predict_text_small(self):
        payload = {"model": "text-small", "input": random.choice(TEXTS)}
        with self.client.post("/predict", json=payload, catch_response=True) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 504:
                resp.failure("worker timeout")
            else:
                resp.failure(f"unexpected {resp.status_code}")

    @task(2)
    def predict_text_large(self):
        payload = {"model": "text-large", "input": random.choice(TEXTS)}
        self.client.post("/predict", json=payload)

    @task(1)
    def predict_image(self):
        payload = {"model": "image-small", "input": "base64_encoded_image_placeholder"}
        self.client.post("/predict", json=payload)

    @task(1)
    def health_check(self):
        self.client.get("/health")
