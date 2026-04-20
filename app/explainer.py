from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

# reuse across warm Lambda invocations — don't init inside the handler
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class AnomalyExplainer:

    def __init__(self, model: str = "gpt-3.5-turbo"):
        # 3.5-turbo is fine here — fast and cheap, gpt-4o if reasoning suffers
        self.model = model

    def explain(self, anomaly: dict) -> str:
        log = anomaly["log_entry"]
        severity = anomaly["severity_score"]
        timestamp = anomaly["timestamp"]

        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior cloud reliability engineer. "
                        "Given anomalous log metrics, write a concise incident summary "
                        "an on-call engineer can act on. Max 3 sentences, no bullet points."
                    ),
                },
                {"role": "user", "content": self._build_prompt(log, severity, timestamp)},
            ],
            max_tokens=150,
            temperature=0.3,  # low temp keeps it factual
        )

        return response.choices[0].message.content.strip()

    def _build_prompt(self, log: dict, severity: float, timestamp: str) -> str:
        # explicit units matter here — vague prompt gets vague output
        return (
            f"Anomaly at {timestamp}, severity {severity}/1.0\n"
            f"error_count:    {log.get('error_count', 0)}\n"
            f"latency_ms:     {log.get('latency_ms', 0)}\n"
            f"memory_used_mb: {log.get('memory_used_mb', 0)}\n"
            f"request_count:  {log.get('request_count', 0)}\n"
            f"source:         {log.get('source', 'unknown')} ({log.get('cloud', 'unknown')})\n\n"
            f"What likely went wrong and what should the on-call engineer check first?"
        )