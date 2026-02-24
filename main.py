from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import smtplib
from email.message import EmailMessage
from uuid import uuid4
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fastapi import Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


# Load environment variables
load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

# ---------------------------
# Google Sheets Setup
# ---------------------------
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name(
    "credentials.json",
    scope
)

client = gspread.authorize(creds)

# You can also use open_by_url() if needed
sheet = client.open("LeaveRequests").sheet1

# ---------------------------
# Temporary in-memory database
# ---------------------------
leave_requests = {}


class LeaveRequest(BaseModel):
    employee_name: str
    employee_email: str
    leave_type: str
    start_date: str
    end_date: str
    reason: str


@app.get("/", response_class=HTMLResponse)
def show_form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})


from fastapi.responses import RedirectResponse


@app.post("/submit-leave-form", response_class=HTMLResponse)
def submit_leave_form(
    request: Request,
    employee_name: str = Form(...),
    employee_email: str = Form(...),
    leave_type: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    reason: str = Form(...)
):

    request_data = LeaveRequest(
        employee_name=employee_name,
        employee_email=employee_email,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason
    )

    # Call existing logic
    submit_leave(request_data)

    # Return success page
    return templates.TemplateResponse("success.html", {"request": request})


@app.post("/submit-leave")
def submit_leave(request: LeaveRequest):

    request_id = str(uuid4())

    leave_requests[request_id] = {
        "data": request.dict(),
        "status": "Pending"
    }

    approve_link = f"http://127.0.0.1:8000/approve/{request_id}"
    reject_link = f"http://127.0.0.1:8000/reject/{request_id}"

    # -------- Send Email to Manager --------
    msg = EmailMessage()
    msg["Subject"] = f"Leave Request from {request.employee_name}"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = EMAIL_ADDRESS  # manager email (yourself for now)

    msg.set_content(f"""
New Leave Request Submitted

Employee Name: {request.employee_name}
Employee Email: {request.employee_email}
Leave Type: {request.leave_type}
Start Date: {request.start_date}
End Date: {request.end_date}
Reason: {request.reason}

Approve:
{approve_link}

Reject:
{reject_link}
""")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

    # -------- Save to Google Sheet --------
    sheet.append_row([
        request_id,
        request.employee_name,
        request.employee_email,
        request.leave_type,
        request.start_date,
        request.end_date,
        request.reason,
        "Pending"
    ])

    return {
        "status": "Leave request submitted",
        "request_id": request_id
    }


@app.get("/approve/{request_id}")
def approve_leave(request_id: str, request: Request):

    if request_id not in leave_requests:
        return {"error": "Request not found"}

    leave_requests[request_id]["status"] = "Approved"

    employee_email = leave_requests[request_id]["data"]["employee_email"]

    # Update Google Sheet
    cell = sheet.find(request_id)
    sheet.update_cell(cell.row, 8, "Approved")

    # Send Email to Employee
    msg = EmailMessage()
    msg["Subject"] = "Your Leave Has Been Approved"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = employee_email
    msg.set_content("Congratulations! Your leave request has been approved.")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

    return templates.TemplateResponse("approved.html", {"request": request})


@app.get("/reject/{request_id}")
def reject_leave(request_id: str, request: Request):

    if request_id not in leave_requests:
        return {"error": "Request not found"}

    leave_requests[request_id]["status"] = "Rejected"

    employee_email = leave_requests[request_id]["data"]["employee_email"]

    # Update Google Sheet
    cell = sheet.find(request_id)
    sheet.update_cell(cell.row, 8, "Rejected")

    # Send Email to Employee
    msg = EmailMessage()
    msg["Subject"] = "Your Leave Has Been Rejected"
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = employee_email
    msg.set_content("Sorry. Your leave request has been rejected.")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)

    return templates.TemplateResponse("rejected.html", {"request": request})