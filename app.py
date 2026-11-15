import os, sqlite3, uuid, json
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort, make_response
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from io import BytesIO

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "proposals.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

DEFAULT_TERMS = (
    "This proposal and the quoted professional fees are valid for a period of two (2) years "
    "from the date of issue. The quoted fees are based on the client's current turnover and "
    "business volume and are subject to upward revision if the client's turnover or business "
    "volume increases, or if the scope or complexity of work changes. Any revised fees will be "
    "communicated to the client and mutually agreed in writing before they take effect."
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "doc", "docx", "xls", "xlsx", "txt"}

class HybridRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

class PgCursor:
    def __init__(self, cursor): self.cursor = cursor
    def fetchone(self):
        row = self.cursor.fetchone()
        return HybridRow(row) if row is not None else None
    def fetchall(self): return [HybridRow(row) for row in self.cursor.fetchall()]

class PgConnection:
    def __init__(self, conn): self.conn = conn
    def execute(self, sql, params=()):
        return PgCursor(self.conn.execute(sql.replace("?", "%s"), params))
    def executescript(self, script):
        for statement in script.split(";"):
            if statement.strip(): self.conn.execute(statement)
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb):
        if exc_type: self.conn.rollback()
        else: self.conn.commit()
        self.conn.close()

def db():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        if psycopg is None:
            raise RuntimeError("PostgreSQL driver missing. Install requirements.txt")
        database_url = database_url.replace("postgres://", "postgresql://", 1)
        return PgConnection(psycopg.connect(database_url, row_factory=dict_row))
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


DEFAULT_SERVICE_ITEMS = [
    {"name": "Refund of accumulated ITC (new)", "amount": 7000.0,
     "scope": "Review GSTR-2B and purchase register; compute eligible refund under Section 54(3) and Rule 89(4); prepare Statement 3A, export invoice statement and annexures; file Form GST RFD-01 and respond to department queries through the sanction order."},
    {"name": "Company audit", "amount": 10000.0,
     "scope": "Conduct statutory audit of the company's financial statements under the Companies Act, 2013; review books and supporting records; issue the auditor's report and related documentation."},
    {"name": "GST returns (Apr 2025 – Mar 2026)", "amount": 12000.0,
     "scope": "Prepare, review and file applicable monthly or quarterly GSTR-1 and GSTR-3B returns for the engagement period, based on records and information provided by the client."},
    {"name": "Professional charges – accounting support", "amount": 8000.0,
     "scope": "Provide routine accounting support, review and organise accounting records, assist with ledger finalisation and provide general accounting advisory during the agreed period."},
    {"name": "Income tax return", "amount": 5000.0,
     "scope": "Compile income and deduction information, prepare the company's income-tax return, review the computation with the client and file the return after approval."},
    {"name": "DIR-3 KYC", "amount": 1500.0,
     "scope": "Complete annual DIR-3 KYC for the applicable directors, verify required details and documents, and file the form with the Ministry of Corporate Affairs."},
    {"name": "ROC compliance", "amount": 5000.0,
     "scope": "Prepare and file applicable ROC forms, including AOC-4, MGT-7A and ADT-1, with the Registrar of Companies based on approved company records."},
]

def parse_service_items(raw):
    try:
        items = json.loads(raw or "[]")
        if isinstance(items, list):
            parsed = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()[:160]
                if not name:
                    continue
                try:
                    amount = max(0.0, float(item.get("amount", 0) or 0))
                except (ValueError, TypeError):
                    amount = 0.0
                parsed.append({"name": name, "amount": amount,
                               "scope": str(item.get("scope", "")).strip()[:5000]})
            return parsed
    except (ValueError, TypeError, json.JSONDecodeError):
        pass
    return []

def proposal_service_items(proposal):
    items = parse_service_items(proposal["service_items"] if "service_items" in proposal.keys() else "[]")
    return items or DEFAULT_SERVICE_ITEMS.copy()

def init_db():
    if os.environ.get("DATABASE_URL"):
        with db() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
                id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, company TEXT, email TEXT, phone TEXT,
                address TEXT, notes TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS proposals (
                id BIGSERIAL PRIMARY KEY, client_id BIGINT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                title TEXT NOT NULL, description TEXT, services TEXT, service_items TEXT DEFAULT '[]', amount DOUBLE PRECISION DEFAULT 0,
                currency TEXT DEFAULT 'INR', status TEXT DEFAULT 'Draft', valid_until TEXT, terms TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attachments (
                id BIGSERIAL PRIMARY KEY, proposal_id BIGINT NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
                original_name TEXT NOT NULL, stored_name TEXT NOT NULL, uploaded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS service_catalog (
                id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, amount DOUBLE PRECISION NOT NULL DEFAULT 0, scope TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            """)
    else:
        with db() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, company TEXT, email TEXT, phone TEXT,
                address TEXT, notes TEXT, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                title TEXT NOT NULL, description TEXT, services TEXT,
                amount REAL DEFAULT 0, currency TEXT DEFAULT 'INR', status TEXT DEFAULT 'Draft',
                valid_until TEXT, terms TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id INTEGER NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
                original_name TEXT NOT NULL, stored_name TEXT NOT NULL, uploaded_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS service_catalog (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                amount REAL NOT NULL DEFAULT 0, scope TEXT DEFAULT '', created_at TEXT NOT NULL
            );
            """)


    # Backward-compatible migration for databases created by earlier versions.
    if os.environ.get("DATABASE_URL"):
        with db() as con:
            con.execute("ALTER TABLE proposals ADD COLUMN IF NOT EXISTS service_items TEXT DEFAULT '[]'")
    else:
        with db() as con:
            columns = [row["name"] for row in con.execute("PRAGMA table_info(proposals)").fetchall()]
            if "service_items" not in columns:
                con.execute("ALTER TABLE proposals ADD COLUMN service_items TEXT DEFAULT '[]'")

    # Backward-compatible migration for the reusable service catalogue.
    if os.environ.get("DATABASE_URL"):
        with db() as con:
            con.execute("ALTER TABLE service_catalog ADD COLUMN IF NOT EXISTS scope TEXT DEFAULT ''")
    else:
        with db() as con:
            columns = [row["name"] for row in con.execute("PRAGMA table_info(service_catalog)").fetchall()]
            if "scope" not in columns:
                con.execute("ALTER TABLE service_catalog ADD COLUMN scope TEXT DEFAULT ''")

    # Seed the reusable service list once; later edits are managed in the website.
    with db() as con:
        count = con.execute("SELECT COUNT(*) FROM service_catalog").fetchone()[0]
        if count == 0:
            for item in DEFAULT_SERVICE_ITEMS:
                con.execute("INSERT INTO service_catalog(name,amount,scope,created_at) VALUES(?,?,?,?)",
                            (item["name"], item["amount"], item["scope"], datetime.now().strftime("%Y-%m-%d %H:%M")))
        # Add suggested scopes to the original seven defaults without overwriting user edits.
        for item in DEFAULT_SERVICE_ITEMS:
            con.execute("UPDATE service_catalog SET scope=? WHERE name=? AND COALESCE(scope,'')=''",
                        (item["scope"], item["name"]))

init_db()

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def get_proposal(pid):
    with db() as con:
        p = con.execute("""SELECT p.*, c.name AS client_name, c.company, c.email AS client_email
                           FROM proposals p JOIN clients c ON c.id=p.client_id WHERE p.id=?""", (pid,)).fetchone()
        if not p: abort(404)
        files = con.execute("SELECT * FROM attachments WHERE proposal_id=? ORDER BY id DESC", (pid,)).fetchall()
    return p, files

@app.route("/")
def dashboard():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    with db() as con:
        stats = {
            "clients": con.execute("SELECT COUNT(*) FROM clients").fetchone()[0],
            "proposals": con.execute("SELECT COUNT(*) FROM proposals").fetchone()[0],
            "accepted": con.execute("SELECT COUNT(*) FROM proposals WHERE status='Accepted'").fetchone()[0],
            "pending": con.execute("SELECT COUNT(*) FROM proposals WHERE status IN ('Sent','Draft')").fetchone()[0],
        }
        sql = """SELECT p.*, c.name AS client_name, c.company FROM proposals p
                 JOIN clients c ON c.id=p.client_id WHERE 1=1"""
        args = []
        if q:
            sql += " AND (p.title LIKE ? OR c.name LIKE ? OR c.company LIKE ?)"
            args += [f"%{q}%"]*3
        if status:
            sql += " AND p.status=?"; args.append(status)
        sql += " ORDER BY p.updated_at DESC LIMIT 100"
        proposals = con.execute(sql, args).fetchall()
        clients = con.execute("SELECT * FROM clients ORDER BY created_at DESC LIMIT 6").fetchall()
    return render_template("dashboard.html", stats=stats, proposals=proposals, clients=clients, q=q, status=status)

@app.route("/clients")
def clients():
    q = request.args.get("q", "").strip()
    with db() as con:
        rows = con.execute("""SELECT c.*, COUNT(p.id) AS proposal_count FROM clients c
            LEFT JOIN proposals p ON p.client_id=c.id
            WHERE c.name LIKE ? OR COALESCE(c.company,'') LIKE ? OR COALESCE(c.email,'') LIKE ?
            GROUP BY c.id ORDER BY c.created_at DESC""", (f"%{q}%",)*3).fetchall()
    return render_template("clients.html", clients=rows, q=q)

@app.route("/clients/new", methods=["GET","POST"])
@app.route("/clients/<int:cid>/edit", methods=["GET","POST"])
def client_form(cid=None):
    client = None
    if cid:
        with db() as con: client = con.execute("SELECT * FROM clients WHERE id=?", (cid,)).fetchone()
        if not client: abort(404)
    if request.method == "POST":
        data = [request.form.get(k,"").strip() for k in ("name","company","email","phone","address","notes")]
        if not data[0]:
            flash("Client name is required.", "error")
        else:
            with db() as con:
                if cid:
                    con.execute("""UPDATE clients SET name=?,company=?,email=?,phone=?,address=?,notes=? WHERE id=?""", (*data,cid))
                else:
                    con.execute("""INSERT INTO clients(name,company,email,phone,address,notes,created_at) VALUES(?,?,?,?,?,?,?)""", (*data,now()))
            flash("Client saved successfully.", "success")
            return redirect(url_for("clients"))
    return render_template("client_form.html", client=client)

@app.post("/clients/<int:cid>/delete")
def client_delete(cid):
    with db() as con: con.execute("DELETE FROM clients WHERE id=?", (cid,))
    flash("Client and associated proposals deleted.", "success")
    return redirect(url_for("clients"))

@app.route("/services", methods=["GET", "POST"])
def service_catalog():
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:160]
        scope = request.form.get("scope", "").strip()[:5000]
        try:
            amount = max(0.0, float(request.form.get("amount", "0") or 0))
        except ValueError:
            amount = -1
        if not name or amount < 0:
            flash("Enter a service name and a valid non-negative fee.", "error")
        else:
            try:
                with db() as con:
                    con.execute("INSERT INTO service_catalog(name,amount,scope,created_at) VALUES(?,?,?,?)",
                                (name, amount, scope, now()))
                flash("Service added to your reusable service list.", "success")
            except Exception as exc:
                if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
                    flash("A service with that name already exists. Edit its existing entry instead.", "error")
                else:
                    raise
        return redirect(url_for("service_catalog"))
    with db() as con:
        services = con.execute("SELECT * FROM service_catalog ORDER BY name").fetchall()
    return render_template("service_catalog.html", services=services)

@app.post("/services/<int:sid>/delete")
def service_catalog_delete(sid):
    with db() as con:
        con.execute("DELETE FROM service_catalog WHERE id=?", (sid,))
    flash("Service removed from the reusable list. Existing proposals are unchanged.", "success")
    return redirect(url_for("service_catalog"))

@app.route("/proposals/new", methods=["GET","POST"])
@app.route("/proposals/<int:pid>/edit", methods=["GET","POST"])
def proposal_form(pid=None):
    proposal = None
    if pid:
        with db() as con:
            proposal = con.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
        if not proposal: abort(404)
    with db() as con:
        clients_list = con.execute("SELECT id,name,company FROM clients ORDER BY name").fetchall()

    if request.method == "POST":
        client_id = request.form.get("client_id", type=int)
        title = request.form.get("title","").strip()
        if not client_id or not title:
            flash("Choose a client and enter a proposal title.", "error")
        else:
            names = request.form.getlist("service_name[]")
            amounts = request.form.getlist("service_amount[]")
            scopes = request.form.getlist("service_scope[]")
            service_items = []
            for index, (name, raw_amount) in enumerate(zip(names, amounts)):
                name = name.strip()
                if not name:
                    continue
                try:
                    amount = max(0.0, float(raw_amount or 0))
                except ValueError:
                    amount = 0.0
                scope = scopes[index].strip()[:5000] if index < len(scopes) else ""
                service_items.append({"name": name[:160], "amount": amount, "scope": scope})
            service_total = round(sum(item["amount"] for item in service_items), 2)
            terms_text = request.form.get("terms", "").strip()
            if not terms_text:
                terms_text = DEFAULT_TERMS
            valid_until = request.form.get("valid_until", "").strip()
            if not valid_until:
                issued = datetime.now().date()
                try:
                    valid_until = issued.replace(year=issued.year + 2).isoformat()
                except ValueError:  # 29 February in a leap year
                    valid_until = issued.replace(year=issued.year + 2, day=28).isoformat()
            fields = (client_id, title, request.form.get("description","").strip(),
                      request.form.get("services","").strip(), json.dumps(service_items, ensure_ascii=False),
                      service_total, request.form.get("currency","INR"), request.form.get("status","Draft"),
                      valid_until, terms_text)
            if pid:
                with db() as con:
                    con.execute("""UPDATE proposals SET client_id=?,title=?,description=?,services=?,service_items=?,amount=?,currency=?,
                    status=?,valid_until=?,terms=?,updated_at=? WHERE id=?""", (*fields,now(),pid))
                flash("Proposal updated with individual service fees.", "success")
                return redirect(url_for("proposal_detail", pid=pid))
            else:
                with db() as con:
                    cur = con.execute("""INSERT INTO proposals(client_id,title,description,services,service_items,amount,currency,status,
                    valid_until,terms,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id""", (*fields,now(),now()))
                    new_id = cur.fetchone()["id"]
                flash("Proposal created with individual service fees.", "success")
                return redirect(url_for("proposal_detail", pid=new_id))

    service_items = proposal_service_items(proposal) if proposal else []
    with db() as con:
        catalog_services = con.execute("SELECT * FROM service_catalog ORDER BY name").fetchall()
    if not proposal and catalog_services:
        service_items = [{"name": row["name"], "amount": row["amount"], "scope": row["scope"] or ""} for row in catalog_services]
    today = datetime.now().date()
    try:
        default_valid_until = today.replace(year=today.year + 2).isoformat()
    except ValueError:
        default_valid_until = today.replace(year=today.year + 2, day=28).isoformat()
    return render_template("proposal_form.html", proposal=proposal, clients=clients_list,
                           service_items=service_items, catalog_services=catalog_services,
                           default_terms=DEFAULT_TERMS, default_valid_until=default_valid_until)

@app.route("/proposals/<int:pid>")
def proposal_detail(pid):
    proposal, files = get_proposal(pid)
    service_items = proposal_service_items(proposal)
    return render_template("proposal_detail.html", proposal=proposal, files=files,
                           service_items=service_items)

@app.post("/proposals/<int:pid>/delete")
def proposal_delete(pid):
    with db() as con:
        rows = con.execute("SELECT stored_name FROM attachments WHERE proposal_id=?", (pid,)).fetchall()
        con.execute("DELETE FROM proposals WHERE id=?", (pid,))
    for row in rows:
        path = os.path.join(UPLOAD_DIR, row["stored_name"])
        if os.path.exists(path): os.remove(path)
    flash("Proposal deleted.", "success")
    return redirect(url_for("dashboard"))

@app.post("/proposals/<int:pid>/duplicate")
def proposal_duplicate(pid):
    p, _ = get_proposal(pid)
    with db() as con:
        cur = con.execute("""INSERT INTO proposals(client_id,title,description,services,service_items,amount,currency,status,valid_until,
            terms,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
            (p["client_id"], p["title"]+" (Copy)", p["description"], p["services"], p["service_items"], p["amount"], p["currency"],
             "Draft", p["valid_until"], p["terms"], now(), now()))
        new_id = cur.fetchone()["id"]
    flash("Proposal duplicated as a new draft.", "success")
    return redirect(url_for("proposal_detail", pid=new_id))

@app.post("/proposals/<int:pid>/upload")
def upload(pid):
    get_proposal(pid)
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Choose a file first.", "error")
    elif "." not in f.filename or f.filename.rsplit(".",1)[1].lower() not in ALLOWED_EXTENSIONS:
        flash("That file type is not allowed.", "error")
    else:
        original = secure_filename(f.filename)
        stored = uuid.uuid4().hex + "_" + original
        f.save(os.path.join(UPLOAD_DIR, stored))
        with db() as con:
            con.execute("INSERT INTO attachments(proposal_id,original_name,stored_name,uploaded_at) VALUES(?,?,?,?)",
                        (pid, original, stored, now()))
        flash("Attachment uploaded.", "success")
    return redirect(url_for("proposal_detail", pid=pid))

@app.route("/uploads/<path:filename>")
def download_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)

@app.post("/attachments/<int:aid>/delete")
def attachment_delete(aid):
    with db() as con:
        row = con.execute("SELECT * FROM attachments WHERE id=?", (aid,)).fetchone()
        if not row: abort(404)
        con.execute("DELETE FROM attachments WHERE id=?", (aid,))
    path = os.path.join(UPLOAD_DIR, row["stored_name"])
    if os.path.exists(path): os.remove(path)
    flash("Attachment deleted.", "success")
    return redirect(url_for("proposal_detail", pid=row["proposal_id"]))

@app.route("/proposals/<int:pid>/pdf")
def proposal_pdf(pid):
    p, _ = get_proposal(pid)
    # sqlite3.Row supports key indexing but not dict.get(); normalize it before
    # the PDF builder accesses proposal fields with .get().
    p = dict(p)
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT, TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, KeepTogether, HRFlowable)
    from xml.sax.saxutils import escape

    buffer = BytesIO()
    navy = colors.HexColor("#17365D")
    blue = colors.HexColor("#2F75B5")
    pale = colors.HexColor("#EAF0F7")
    ink = colors.HexColor("#263445")
    muted = colors.HexColor("#667085")
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
                            topMargin=22*mm, bottomMargin=20*mm,
                            title=f"Proposal - {p['title']}", author="A Neha & Associates Chartered Accountants")
    base = getSampleStyleSheet()
    styles = {
        "brand": ParagraphStyle("Brand", parent=base["Title"], fontName="Helvetica-Bold", fontSize=19,
                                 leading=23, textColor=navy, alignment=TA_LEFT, spaceAfter=3),
        "subtitle": ParagraphStyle("Subtitle", parent=base["Normal"], fontSize=9.5, leading=14,
                                    textColor=muted, spaceAfter=12),
        "title": ParagraphStyle("ProposalTitle", parent=base["Heading1"], fontSize=17, leading=22,
                                 textColor=ink, spaceBefore=8, spaceAfter=8),
        "section": ParagraphStyle("Section", parent=base["Heading2"], fontSize=14.5, leading=19,
                                   textColor=navy, spaceBefore=12, spaceAfter=6, keepWithNext=True),
        "body": ParagraphStyle("BodyCustom", parent=base["BodyText"], fontSize=11.5, leading=17,
                                textColor=ink, alignment=TA_JUSTIFY, spaceAfter=4),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontSize=9.5, leading=13, textColor=muted),
        "cell": ParagraphStyle("Cell", parent=base["BodyText"], fontSize=10.2, leading=14, textColor=ink, alignment=TA_JUSTIFY),
        "cellright": ParagraphStyle("CellRight", parent=base["BodyText"], fontSize=10.2, leading=14,
                                     alignment=TA_RIGHT, textColor=ink),
        "cellbold": ParagraphStyle("CellBold", parent=base["BodyText"], fontName="Helvetica-Bold",
                                    fontSize=10.2, leading=14, textColor=ink),
        "tableheader": ParagraphStyle("TableHeader", parent=base["BodyText"], fontName="Helvetica-Bold",
                                       fontSize=10, leading=13.5, textColor=colors.white),
        "total": ParagraphStyle("Total", parent=base["BodyText"], fontName="Helvetica-Bold",
                                fontSize=10.8, leading=14, textColor=navy),
    }
    def pdf_text(value):
        # Helvetica in ReportLab's built-in fonts cannot render the Indian rupee glyph.
        # Convert it to a readable ASCII currency label before creating Paragraphs.
        return str(value or "").replace("₹", "INR ").replace("\u20b9", "INR ")

    def money(value):
        symbol = (p.get("currency") or "INR").upper()
        return f"INR {value:,.2f}" if "INR" in symbol or "₹" in symbol else f"{escape(p.get('currency') or '')} {value:,.2f}"

    story = [Paragraph("A NEHA &amp; ASSOCIATES", styles["brand"]),
             Paragraph("CHARTERED ACCOUNTANTS  |  PROFESSIONAL SERVICES PROPOSAL", styles["subtitle"]),
             HRFlowable(width="100%", thickness=1.2, color=blue, spaceAfter=12),
             Paragraph(escape(p["title"] or "Professional Services Proposal"), styles["title"])]
    client_line = "<b>Prepared for:</b> " + escape(p.get("client_name") or "")
    if p.get("company"):
        client_line += "<br/><b>Company:</b> " + escape(p["company"])
    client_line += "<br/><b>Proposal date:</b> " + escape(str(p.get("created_at") or ""))
    if p.get("status"):
        client_line += " &nbsp;&nbsp; <b>Status:</b> " + escape(str(p["status"]))
    story += [Paragraph(client_line, styles["body"]), Spacer(1, 8)]

    # Standard firm profile: included in every proposal PDF, independent of
    # the client-specific engagement description entered on the proposal form.
    story += [Paragraph("Overview: About A Neha &amp; Associates", styles["section"]),
              Paragraph(escape("A Neha & Associates is a Chartered Accountancy firm based in Faridabad. Since 2019 we have provided assurance, taxation, compliance and advisory services to businesses and individuals. We aim to be a long-term financial partner to our clients, helping them stay compliant and make well-informed decisions as they grow."), styles["body"]),
              Paragraph("Our Services", styles["section"])]
    service_profile = [
        ("Audit &amp; Assurance", "Statutory audit and internal audit"),
        ("Direct Taxation", "Income tax compliance, tax planning, assessments and representation"),
        ("GST", "Registration, return filing, reconciliations, advisory and departmental proceedings"),
        ("Corporate &amp; Regulatory Compliance", "ROC filings, company law matters and FEMA compliance"),
        ("Accounting &amp; Payroll", "Bookkeeping, financial statement preparation and payroll processing"),
        ("Advisory", "Startup advisory, business valuation and Virtual CFO services"),
    ]
    profile_rows = [[Paragraph("<b>" + name + ":</b> " + desc, styles["body"])] for name, desc in service_profile]
    profile_table = Table(profile_rows, colWidths=[174*mm], hAlign="LEFT")
    profile_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F7F9FC")),
        ("BOX", (0,0), (-1,-1), 0.35, colors.HexColor("#D8E0EA")),
        ("INNERGRID", (0,0), (-1,-1), 0.25, colors.HexColor("#E5EAF1")),
        ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))
    story += [profile_table, Paragraph("Our Approach", styles["section"]),
              Paragraph("<b>A dedicated partner for every client.</b> Each engagement is led by a partner who is your single point of contact, so you get senior attention and continuity throughout.", styles["body"]),
              Paragraph("<b>Tech-enabled processes.</b> We use digital tools for data collection, compliance tracking and reporting, which makes our work faster, more accurate and transparent, and keeps you updated on every deadline.", styles["body"])]
    if p.get("description"):
        story += [Paragraph("Engagement Overview", styles["section"]),
                  Paragraph(escape(pdf_text(p["description"])).replace("\n", "<br/>"), styles["body"])]

    service_items = proposal_service_items(p)
    data = [[Paragraph("SERVICE &amp; SCOPE OF WORK", styles["tableheader"]),
             Paragraph("PROFESSIONAL FEE", styles["tableheader"])]]
    for item in service_items:
        label = f"<b>{escape(str(item.get('name') or 'Service'))}</b>"
        if item.get("scope"):
            label += "<br/>" + escape(str(item["scope"])).replace("\n", "<br/>")
        data.append([Paragraph(label, styles["cell"]), Paragraph(money(float(item.get("amount") or 0)), styles["cellright"])])
    subtotal = sum(float(item.get("amount") or 0) for item in service_items)
    igst = subtotal * 0.18
    data.extend([
        [Paragraph("Subtotal", styles["cellbold"]), Paragraph(money(subtotal), styles["cellright"])],
        [Paragraph("IGST (18%)", styles["cell"]), Paragraph(money(igst), styles["cellright"])],
        [Paragraph("TOTAL PAYABLE", styles["total"]), Paragraph(money(subtotal + igst), styles["total"])],
    ])
    if p.get("valid_until"):
        data.append([Paragraph("Proposal valid until", styles["cellbold"]),
                     Paragraph(escape(str(p["valid_until"])), styles["cellright"])])
    table = Table(data, colWidths=[125*mm, 49*mm], repeatRows=1, hAlign="LEFT")
    subtotal_idx = len(data) - (4 if p.get("valid_until") else 3)
    igst_idx, total_idx = subtotal_idx + 1, subtotal_idx + 2
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), navy),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("ROWBACKGROUNDS", (0,1), (-1,subtotal_idx-1), [colors.white, colors.HexColor("#F7F9FC")]),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#D8E0EA")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("TOPPADDING", (0,0), (-1,-1), 7), ("BOTTOMPADDING", (0,0), (-1,-1), 7),
        ("BACKGROUND", (0,subtotal_idx), (-1,subtotal_idx), pale),
        ("BACKGROUND", (0,igst_idx), (-1,igst_idx), colors.HexColor("#F7F9FC")),
        ("BACKGROUND", (0,total_idx), (-1,total_idx), colors.HexColor("#E4ECF5")),
        ("LINEABOVE", (0,subtotal_idx), (-1,subtotal_idx), 0.8, blue),
    ]))
    story += [Paragraph("Services and professional fees", styles["section"]), table]

    if p.get("terms"):
        story += [Paragraph("Terms &amp; Conditions", styles["section"]),
                  Paragraph(escape(pdf_text(p["terms"])).replace("\n", "<br/>"), styles["body"])]

    company_name = p.get("company") or p.get("client_name") or "Client"
    signature_data = [
        [Paragraph("<b>For A Neha &amp; Associates Chartered Accountants</b>", styles["cell"]),
         Paragraph("<b>Accepted by:</b> " + escape(company_name), styles["cell"])],
        [Paragraph("<br/><br/>________________________________<br/>Proprietor<br/>Membership No.: __________________", styles["cell"]),
         Paragraph("<br/><br/>________________________________<br/>Director / Authorised Signatory<br/>Date: __________________", styles["cell"])],
    ]
    signature = Table(signature_data, colWidths=[87*mm, 87*mm], hAlign="LEFT")
    signature.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#F7F9FC")),
        ("BOX", (0,0), (-1,-1), 0.5, colors.HexColor("#D8E0EA")),
        ("INNERGRID", (0,0), (-1,-1), 0.4, colors.HexColor("#D8E0EA")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 10), ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("TOPPADDING", (0,0), (-1,-1), 10), ("BOTTOMPADDING", (0,0), (-1,-1), 10),
    ]))
    story += [Paragraph("Acceptance", styles["section"]),
              Paragraph("Please sign and return a copy to confirm acceptance.", styles["body"]),
              signature]

    def page_decor(canvas, document):
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(colors.HexColor("#D8E0EA"))
        canvas.setLineWidth(0.5)
        canvas.line(18*mm, 14*mm, width-18*mm, 14*mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(muted)
        canvas.drawString(18*mm, 9*mm, "A Neha & Associates Chartered Accountants")
        canvas.drawRightString(width-18*mm, 9*mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=page_decor, onLaterPages=page_decor)
    response = make_response(buffer.getvalue())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'attachment; filename="proposal-{pid}.pdf"'
    return response

@app.errorhandler(413)
def too_large(e):
    flash("File is too large. Maximum upload size is 16 MB.", "error")
    return redirect(request.referrer or url_for("dashboard"))

if __name__ == "__main__":
    app.run(debug=True)
