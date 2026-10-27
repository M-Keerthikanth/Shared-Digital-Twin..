# Shared Digital Twin Dashboard for MSME Industrial Clusters - B.Tech Micro Project 6
# Flask + SQLite version (for deploying on Render)
import os, sqlite3, hashlib, csv, io, threading, time
from flask import Flask, request, session, redirect, render_template_string, Response, abort

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "micro-project-key")
DB = "twin.db"

def sha(p): return hashlib.sha256(p.encode()).hexdigest()

def q(sql, args=()):
    """Run any SQL query. Returns (column names, rows)."""
    con = sqlite3.connect(DB)
    cur = con.execute(sql, args)
    rows = cur.fetchall()
    head = [d[0] for d in cur.description] if cur.description else []
    con.commit(); con.close()
    return head, rows

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT);
CREATE TABLE IF NOT EXISTS factories(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, location TEXT, industry TEXT, capacity INT);
CREATE TABLE IF NOT EXISTS machines(id INTEGER PRIMARY KEY AUTOINCREMENT, factory_id INT, name TEXT, type TEXT, status TEXT, utilization REAL);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, category TEXT);
CREATE TABLE IF NOT EXISTS production(id INTEGER PRIMARY KEY AUTOINCREMENT, factory_id INT, product_id INT, planned INT, produced INT, rejected INT, shift TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS employees(id INTEGER PRIMARY KEY AUTOINCREMENT, factory_id INT, name TEXT, role TEXT, skill TEXT);
CREATE TABLE IF NOT EXISTS energy(id INTEGER PRIMARY KEY AUTOINCREMENT, factory_id INT, log_date TEXT, kwh REAL, cost REAL);
CREATE TABLE IF NOT EXISTS defects(id INTEGER PRIMARY KEY AUTOINCREMENT, factory_id INT, defect_type TEXT, reason TEXT, qty INT);
CREATE TABLE IF NOT EXISTS resources(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type TEXT, available TEXT, location TEXT);
CREATE TABLE IF NOT EXISTS logistics(id INTEGER PRIMARY KEY AUTOINCREMENT, factory_id INT, vehicle TEXT, destination TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS login_log(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, success INT, time TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, action TEXT, time TEXT DEFAULT CURRENT_TIMESTAMP);
"""
SEED = """
INSERT INTO users(username,password,role) VALUES('admin','HASH1','Cluster Administrator'),('manager','HASH2','Factory Manager');
INSERT INTO factories(name,location,industry,capacity) VALUES('Apex Auto Components','Peenya','Automotive',5000),('Bharat Fabrication','Jigani','Fabricated Metal',3000),('Polyform Plastics','Hosur Road','Plastic Parts',4000);
INSERT INTO machines(factory_id,name,type,status,utilization) VALUES(1,'CNC-01','CNC','Running',86),(1,'Press-02','Press','Maintenance',0),(2,'Welder-01','Welding','Running',72),(2,'Laser-01','Cutting','Idle',35),(3,'Mold-01','Injection','Running',91);
INSERT INTO products(name,category) VALUES('Brake Bracket','Automotive'),('Steel Frame','Fabricated'),('Housing Cover','Plastic');
INSERT INTO production(factory_id,product_id,planned,produced,rejected,shift,status) VALUES(1,1,1000,950,30,'Day','In Progress'),(2,2,500,260,25,'Night','Delayed'),(3,3,2000,1980,40,'Day','Completed');
INSERT INTO employees(factory_id,name,role,skill) VALUES(1,'Ravi K','Operator','CNC'),(2,'Meena S','Welder','Welding'),(3,'Arun P','Supervisor','Molding');
INSERT INTO energy(factory_id,log_date,kwh,cost) VALUES(1,date('now'),310.5,2484),(2,date('now'),420,3360),(3,date('now'),510,4080);
INSERT INTO defects(factory_id,defect_type,reason,qty) VALUES(1,'Dimensional','Tool wear',30),(2,'Weld','Porosity',25);
INSERT INTO resources(name,type,available,location) VALUES('5-Axis CNC','Machine','Yes','Common Hall'),('Cluster Warehouse','Warehouse','Yes','Block D'),('Tempo-KA01','Vehicle','No','Gate 1'),('Skilled Welders','Labor Pool','Yes','Pool');
INSERT INTO logistics(factory_id,vehicle,destination,status) VALUES(1,'Truck-12','Chennai','In Transit'),(2,'Tempo-03','Mysuru','Delayed'),(3,'Truck-07','Pune','Delivered');
"""

def init_db():
    con = sqlite3.connect(DB); con.executescript(SCHEMA)
    if not con.execute("SELECT 1 FROM users").fetchone():
        con.executescript(SEED.replace("HASH1", sha("admin123")).replace("HASH2", sha("manager123")))
    con.commit(); con.close()

# page name -> (title, SQL to show, table for add/delete, columns for add form)
PAGES = {
 "factories": ("Factories", "SELECT id ID,name Name,location Location,industry Industry,capacity Capacity FROM factories", "factories", "name,location,industry,capacity"),
 "machines": ("Machines", "SELECT m.id ID,f.name Factory,m.name Machine,m.type Type,m.status Status,ROUND(m.utilization,1) 'Util %' FROM machines m JOIN factories f ON f.id=m.factory_id", "machines", "factory_id,name,type,status,utilization"),
 "production": ("Production", "SELECT o.id ID,f.name Factory,p.name Product,o.planned Planned,o.produced Produced,o.rejected Rejected,o.shift Shift,o.status Status FROM production o JOIN factories f ON f.id=o.factory_id JOIN products p ON p.id=o.product_id", "production", "factory_id,product_id,planned,produced,rejected,shift,status"),
 "products": ("Products", "SELECT id ID,name Name,category Category FROM products", "products", "name,category"),
 "employees": ("Employees", "SELECT e.id ID,f.name Factory,e.name Name,e.role Role,e.skill Skill FROM employees e JOIN factories f ON f.id=e.factory_id", "employees", "factory_id,name,role,skill"),
 "energy": ("Energy", "SELECT e.id ID,f.name Factory,e.log_date Date,e.kwh kWh,e.cost Cost FROM energy e JOIN factories f ON f.id=e.factory_id", "energy", "factory_id,log_date,kwh,cost"),
 "defects": ("Quality / Defects", "SELECT d.id ID,f.name Factory,d.defect_type Defect,d.reason Reason,d.qty Qty FROM defects d JOIN factories f ON f.id=d.factory_id", "defects", "factory_id,defect_type,reason,qty"),
 "resources": ("Shared Resources", "SELECT id ID,name Name,type Type,available Available,location Location FROM resources", "resources", "name,type,available,location"),
 "logistics": ("Logistics", "SELECT l.id ID,f.name Factory,l.vehicle Vehicle,l.destination Destination,l.status Status FROM logistics l JOIN factories f ON f.id=l.factory_id", "logistics", "factory_id,vehicle,destination,status"),
 "bottlenecks": ("Bottlenecks",
   "SELECT 'Machine Downtime' Type, name||' is '||status Detail FROM machines WHERE status<>'Running' UNION ALL "
   "SELECT 'Production Delay','Order '||id||' at '||ROUND(produced*100.0/planned)||'% of plan' FROM production WHERE produced<planned*0.8 UNION ALL "
   "SELECT 'High Defect Rate','Order '||id||' rejects '||ROUND(rejected*100.0/produced,1)||'%' FROM production WHERE produced>0 AND rejected*100.0/produced>5 UNION ALL "
   "SELECT 'Logistics Delay',vehicle||' to '||destination FROM logistics WHERE status='Delayed'", None, None),
 "users": ("Users", "SELECT id ID,username Username,role Role FROM users", "users", "username,password,role"),
 "audit": ("Audit Log", "SELECT username User,action Action,time Time FROM audit_log ORDER BY id DESC LIMIT 50", None, None),
}

def can_edit(): return session.get("role") in ("Cluster Administrator", "Factory Manager")
def log(action): q("INSERT INTO audit_log(username,action) VALUES(?,?)", (session.get("user"), action))

STYLE = """<style>body{font-family:Arial;margin:0}nav{background:#ddd;padding:8px}nav a{margin-right:10px}main{padding:15px}
table{border-collapse:collapse}th,td{border:1px solid black;padding:5px}th{background:#eee}.k{display:flex;gap:10px;flex-wrap:wrap}
.c{border:1px solid black;padding:8px}.bar{background:#ddd;width:300px;height:12px}.bar i{display:block;height:12px;background:blue}input{margin:2px}</style>"""
NAV = STYLE + """<nav><b>MSME Digital Twin</b> | <a href="/">Dashboard</a>{% for k,v in pages.items() %}<a href="/{{k}}">{{v[0]}}</a>{% endfor %}
<span style="float:right">{{session.user}} ({{session.role}}) <a href="/logout">Logout</a></span></nav><main>"""
LOGIN = """<body style="font-family:Arial;margin:40px"><h2>Shared Digital Twin Dashboard for MSME Industrial Clusters</h2><h3>Login</h3>
<p style="color:red">{{err}}</p><form method="post">Username: <input name="username" required><br><br>
Password: <input name="password" type="password" required><br><br><button>Login</button></form><p>Demo login: admin / admin123</p></body>"""
DASH = NAV + """<meta http-equiv="refresh" content="15"><h2>Cluster Productivity Dashboard</h2>
<div class="k">{% for k,v in kpis.items() %}<div class="c"><small>{{k}}</small><h2>{{v}}</h2></div>{% endfor %}</div>
<h3>Production vs Plan</h3>{% for n,p,pl in bars %}<p>{{n}}: {{p}} / {{pl}}</p><div class="bar"><i style="width:{{ [100, (p*100/pl)|int]|min }}%"></i></div>{% endfor %}</main>"""
LIST = NAV + """<h2>{{title}}</h2><p style="color:red">{{err or ''}}</p><a href="?csv=1">Export CSV</a><br><br>
{% if edit and cols %}<form method="post" action="/{{page}}/add">{% for c in cols %}<input name="{{c}}" placeholder="{{c}}" type="{{'password' if c=='password' else 'text'}}">{% endfor %}<button>Add</button></form><br>{% endif %}
{% set dele = edit and cols and head[0]=='ID' %}<table><tr>{% for h in head %}<th>{{h}}</th>{% endfor %}{% if dele %}<th></th>{% endif %}</tr>
{% for r in rows %}<tr>{% for v in r %}<td>{{v}}</td>{% endfor %}{% if dele %}<td><a href="/{{page}}/delete/{{r[0]}}" onclick="return confirm('Delete?')">Delete</a></td>{% endif %}</tr>{% endfor %}</table></main>"""

@app.before_request
def need_login():
    if "user" not in session and request.endpoint not in ("login", "static"):
        return redirect("/login")

@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        u, p = request.form["username"], sha(request.form["password"])
        rows = q("SELECT role FROM users WHERE username=? AND password=?", (u, p))[1]
        q("INSERT INTO login_log(username,success) VALUES(?,?)", (u, 1 if rows else 0))
        if rows:
            session["user"], session["role"] = u, rows[0][0]
            return redirect("/")
        err = "Invalid username or password"
    return render_template_string(LOGIN, err=err)

@app.route("/logout")
def logout():
    session.clear(); return redirect("/login")

@app.route("/")
def dashboard():
    one = lambda sql: q(sql)[1][0][0] or 0
    kpis = {"Factories": one("SELECT COUNT(*) FROM factories"),
            "Machines running": f"{one('SELECT SUM(status=\"Running\") FROM machines')} / {one('SELECT COUNT(*) FROM machines')}",
            "Avg utilization %": round(one("SELECT AVG(utilization) FROM machines"), 1),
            "Units produced": one("SELECT SUM(produced) FROM production"),
            "Defect rate %": round(one("SELECT SUM(rejected)*100.0/SUM(produced) FROM production"), 2),
            "Energy (kWh)": one("SELECT SUM(kwh) FROM energy")}
    bars = q("SELECT f.name,SUM(o.produced),SUM(o.planned) FROM production o JOIN factories f ON f.id=o.factory_id GROUP BY f.name")[1]
    return render_template_string(DASH, kpis=kpis, bars=bars, pages=PAGES)

@app.route("/<page>")
def show(page):
    if page not in PAGES: abort(404)
    title, sql, table, cols = PAGES[page]
    head, rows = q(sql)
    if request.args.get("csv"):
        out = io.StringIO(); w = csv.writer(out); w.writerow(head); w.writerows(rows)
        return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={page}.csv"})
    return render_template_string(LIST, title=title, head=head, rows=rows, page=page, pages=PAGES,
                                  cols=cols.split(",") if cols else [], edit=can_edit(), err=request.args.get("err"))

def check(page):
    if page not in PAGES or not PAGES[page][2] or not can_edit(): abort(403)
    if page == "users" and session["role"] != "Cluster Administrator": abort(403)

@app.route("/<page>/add", methods=["POST"])
def add(page):
    check(page)
    table, cols = PAGES[page][2], PAGES[page][3].split(",")
    vals = [request.form.get(c) or None for c in cols]
    if table == "users" and vals[1]: vals[1] = sha(vals[1])
    try:
        q(f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))})", vals)
        log("Added to " + table)
    except Exception:
        return redirect(f"/{page}?err=Could not save, check the values")
    return redirect("/" + page)

@app.route("/<page>/delete/<int:rid>")
def delete(page, rid):
    check(page)
    q(f"DELETE FROM {PAGES[page][2]} WHERE id=?", (rid,)); log(f"Deleted {PAGES[page][2]} #{rid}")
    return redirect("/" + page)

def simulate():
    """Background thread (multithreading): changes machine utilization every 10 s like live IoT data."""
    while True:
        time.sleep(10)
        try: q("UPDATE machines SET utilization=MIN(100,MAX(20,utilization+(abs(random())%10)-5)) WHERE status='Running'")
        except Exception: pass

init_db()
threading.Thread(target=simulate, daemon=True).start()

if __name__ == "__main__":
    app.run(debug=True)
