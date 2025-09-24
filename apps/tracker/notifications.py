# Simple notification stubs (expand for real SMS/WhatsApp integrations)
import os

def notify_absence(student_name: str, phone: str, date_str: str):
    # Here you would integrate with Twilio or WhatsApp Business API
    # (Read TWILIO_* from environment)
    # For demo, we just print:
    print(f"[NOTIFY] {student_name} was absent on {date_str}. Send SMS/WA to {phone}")
