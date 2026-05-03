import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive",
]

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json",
    scopes=SCOPES,
    redirect_uri="http://localhost:8080/",
)

creds = flow.run_local_server(port=8080)
print(f"REFRESH_TOKEN={creds.refresh_token}")