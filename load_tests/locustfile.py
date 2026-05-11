import random

from locust import HttpUser, between, constant, task

SHORT_TEXTS = [
    "this movie was absolutely fantastic",
    "terrible experience, would not recommend",
    "it was okay, nothing particularly special",
    "best product I have ever bought",
    "complete waste of money and time",
    "not what I expected but pleasantly surprised",
]

LONG_TEXTS = [
    (
        "An extensive and detailed analysis of the film covering cinematography, "
        "narrative structure, character development, and thematic depth. The director "
        "manages to weave together multiple storylines while maintaining coherence. "
        "The performances are nuanced and the soundtrack complements each scene."
    ),
    (
        "This product exceeded every expectation I had going into the purchase. "
        "The build quality is exceptional and the attention to detail is remarkable. "
        "After six months of daily use I can confidently say this is the best "
        "investment I have made this year. Customer support was also outstanding."
    ),
]


def _post(client, model: str, text: str) -> None:
    with client.post("/predict", json={"model": model, "input": text}, catch_response=True) as resp:
        if resp.status_code == 200:
            resp.success()
        elif resp.status_code == 503:
            resp.failure("circuit open")
        elif resp.status_code == 504:
            resp.failure("timeout")
        else:
            resp.failure(f"http {resp.status_code}")


class BaselineUser(HttpUser):
    """Steady mixed traffic across all three models — nominal production load."""

    wait_time = between(0.1, 0.5)

    @task(4)
    def predict_text_small(self):
        _post(self.client, "text-small", random.choice(SHORT_TEXTS))

    @task(2)
    def predict_text_large(self):
        _post(self.client, "text-large", random.choice(LONG_TEXTS))

    @task(1)
    def predict_image(self):
        _post(self.client, "image-small", "base64_image_placeholder")

    @task(1)
    def health_check(self):
        self.client.get("/health")


class BurstUser(HttpUser):
    """High-frequency text-small traffic — tests throughput ceiling."""

    wait_time = between(0.01, 0.05)

    @task(8)
    def predict_text_small(self):
        _post(self.client, "text-small", random.choice(SHORT_TEXTS))

    @task(2)
    def predict_text_large(self):
        _post(self.client, "text-large", random.choice(LONG_TEXTS))


class OverloadUser(HttpUser):
    """Zero-wait sustained load — saturates the worker queue and forces timeouts."""

    wait_time = constant(0)

    @task
    def predict_text_small(self):
        _post(self.client, "text-small", random.choice(SHORT_TEXTS))
