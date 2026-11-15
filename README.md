# ProposalDesk — Client Proposal Manager

A responsive Flask website for managing clients and multiple proposals per client. Data is stored in SQLite (`proposals.db`) and uploaded files are stored in `uploads/`.

## Features
- Dashboard with client/proposal counts and recent proposals
- Client create, edit, delete and search
- Multiple proposals per client
- Proposal description, services, amount, currency, validity date, terms and status
- Draft / Sent / Accepted / Rejected status tracking
- Search and status filters
- Duplicate and delete proposals
- Upload and download supporting files (16 MB max)
- Download proposal as PDF
- Responsive layout for phones, tablets and laptops

## Run locally

Requires Python 3.10 or newer.

```bash
# 1. Open this folder in Terminal / VS Code
# 2. Create a virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate

# macOS / Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the website
python app.py
```

Open http://127.0.0.1:5000 in your browser.

## Data and backups
- Client and proposal data: `proposals.db`
- Uploaded files: `uploads/`
Back up both regularly. Deleting a client deletes that client's proposals and attachments from the database; the associated attachment files are removed when deleting an individual proposal. For a full backup, stop the server and copy the database and uploads folder.

## Before public deployment
This is a starter application intended for local/private use. Before putting it on the public internet:
- Set a long random `SECRET_KEY` environment variable.
- Add user login and role-based access; the starter app does not include authentication.
- Use HTTPS and a production WSGI server (such as Gunicorn or Waitress), not Flask's development server.
- Configure automated database and upload backups.
- Add CSRF protection, malware scanning for uploads, and appropriate privacy/data-retention controls.


## Public deployment
See [DEPLOY_GITHUB_RENDER.md](DEPLOY_GITHUB_RENDER.md) for GitHub + Render + PostgreSQL deployment instructions.


## Individual service fees

The proposal builder now stores seven editable service-wise fees, calculates the professional-fee subtotal and 18% IGST, and displays a service selector with an individual fee calculation on each proposal detail page. The PDF export includes the service-wise fee breakdown.

**Payment collection is not connected yet.** The detail page currently calculates the selected service amount; to accept real payments, configure a payment provider such as Razorpay and add its server-side checkout/webhook flow. Do not treat the selector as proof of payment.


## Reusable services and fees

Open **Services & fees** from the left navigation to add reusable service names and default fees. These entries are stored in the application's database and appear as suggestions when creating a proposal. Choose a saved name to automatically fill its default fee, or type a one-off service name and fee. Use **Add another service** to include as many line items as needed. The proposal subtotal and 18% IGST update automatically. Removing an item from the reusable catalogue does not alter existing proposals.


### Scope of services
The reusable Services & fees catalogue now stores a scope/description for every service. When a saved service is selected in a proposal, its default fee and scope are copied into that proposal. The scope can then be edited for that specific proposal. Service-wise scope and fees are shown on the proposal details page and included in the PDF.

## Automatic proposal validity and turnover clause
The proposal form pre-fills a two-year validity date and standard turnover-based fee revision clause. Both can be edited per proposal. See `TERMS_UPDATE_GUIDE.md`.
