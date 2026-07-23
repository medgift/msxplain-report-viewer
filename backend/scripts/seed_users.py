"""Provision a user in self-hosted GoTrue without SMTP (team / invite-only mode).

Signup is disabled publicly (GOTRUE_DISABLE_SIGNUP=true); admins create users
through the GoTrue Admin API using the service_role key. The user is created
pre-confirmed (email_confirm=true) so no confirmation email is needed.

Usage (inside the backend container or with the env vars set):
    python scripts/seed_users.py <email> <password>

Environment:
    SUPABASE_AUTH_URL         internal GoTrue base URL (default http://supabase-auth:9999)
    SUPABASE_SERVICE_ROLE_KEY service_role JWT
"""
import os
import sys

import requests

AUTH_URL = os.getenv("SUPABASE_AUTH_URL", "http://supabase-auth:9999").rstrip("/")
SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def create_user(email: str, password: str) -> None:
    if not SERVICE_ROLE_KEY:
        sys.exit("SUPABASE_SERVICE_ROLE_KEY is not set")

    resp = requests.post(
        f"{AUTH_URL}/admin/users",
        headers={
            "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
            "apikey": SERVICE_ROLE_KEY,
            "Content-Type": "application/json",
        },
        json={"email": email, "password": password, "email_confirm": True},
        timeout=30,
    )
    if resp.status_code in (200, 201):
        user = resp.json()
        print(f"Created user {email} (id={user.get('id')})")
    else:
        sys.exit(f"Failed to create user ({resp.status_code}): {resp.text}")


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python scripts/seed_users.py <email> <password>")
    create_user(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
