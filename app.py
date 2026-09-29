from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3, json, os
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
DB = "database.db"

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS exams(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        duration INTEGER NOT NULL,
        question_limit INTEGER DEFAULT 50,
        start_time TEXT,
        end_time TEXT
    );

    CREATE TABLE IF NOT EXISTS questions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id INTEGER,
        question TEXT NOT NULL,
        option_a TEXT,
        option_b TEXT,
        option_c TEXT,
        option_d TEXT,
        correct_answer INTEGER
    );

    CREATE TABLE IF NOT EXISTS answers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        exam_id INTEGER,
        question_id INTEGER,
        answer INTEGER
    );

    CREATE TABLE IF NOT EXISTS checkpoints(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        exam_id INTEGER,
        current_question INTEGER,
        answers TEXT,
        remaining_time INTEGER,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS results(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        exam_id INTEGER,
        score INTEGER,
        total INTEGER,
        percentage REAL,
        status TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS failure_logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        exam_id INTEGER,
        failure_type TEXT,
        rollback_time TEXT,
        action_taken TEXT
    );
    """)

    columns = conn.execute("PRAGMA table_info(exams)").fetchall()
    column_names = [column["name"] for column in columns]

    if "question_limit" not in column_names:
        conn.execute(
            "ALTER TABLE exams ADD COLUMN question_limit INTEGER DEFAULT 50"
        )

    try:
        conn.execute(
            "INSERT INTO users(name,username,password,role) VALUES(?,?,?,?)",
            ("Demo Student", "student", "student123", "student")
        )
    except sqlite3.IntegrityError:
        pass

    try:
        conn.execute(
            "INSERT INTO users(name,username,password,role) VALUES(?,?,?,?)",
            ("System Admin", "admin", "admin123", "admin")
        )
    except sqlite3.IntegrityError:
        pass

    if conn.execute("SELECT COUNT(*) FROM exams").fetchone()[0] == 0:
        cur = conn.execute(
            """INSERT INTO exams
               (title,duration,question_limit,start_time,end_time)
               VALUES(?,?,?,?,?)""",
            ("Java Programming", 10, 5, "", "")
        )

        eid = cur.lastrowid

        qs = [
            ("Which keyword creates an object in Java?",
             "class", "new", "this", "void", 1),

            ("Which method is the entry point of a Java program?",
             "start()", "run()", "main()", "init()", 2),

            ("Which type stores true or false?",
             "int", "boolean", "char", "float", 1),

            ("Which symbol ends a Java statement?",
             ";", ":", ".", ",", 0),

            ("Which keyword is used for inheritance?",
             "extends", "inherits", "implements", "super", 0)
        ]

        conn.executemany(
            """INSERT INTO questions
               (exam_id,question,option_a,option_b,option_c,option_d,correct_answer)
               VALUES(?,?,?,?,?,?,?)""",
            [(eid, *q) for q in qs]
        )

    conn.commit()
    conn.close()

def login_required(role=None):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))

            if role and session.get("role") != role:
                return redirect(url_for("index"))

            return f(*args, **kwargs)

        return wrapper

    return deco

@app.route("/")
def index():
    if session.get("role") == "admin":
        return redirect(url_for("admin_dashboard"))

    if session.get("role") == "student":
        return redirect(url_for("student_dashboard"))

    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = db()

        user = conn.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (u, p)
        ).fetchone()

        conn.close()

        if user:
            session.update(
                user_id=user["id"],
                name=user["name"],
                role=user["role"]
            )

            return redirect(url_for("index"))

        return render_template(
            "login.html",
            error="Invalid username or password"
        )

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            conn = db()

            conn.execute(
                """INSERT INTO users(name,username,password,role)
                   VALUES(?,?,?,'student')""",
                (
                    request.form["name"],
                    request.form["username"],
                    request.form["password"]
                )
            )

            conn.commit()
            conn.close()

            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            return render_template(
                "register.html",
                error="Username already exists"
            )

    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/student")
@login_required("student")
def student_dashboard():
    conn = db()

    exams = conn.execute(
        "SELECT * FROM exams"
    ).fetchall()

    conn.close()

    return render_template(
        "student_dashboard.html",
        exams=exams
    )

@app.route("/exam/<int:exam_id>")
@login_required("student")
def exam(exam_id):
    conn = db()

    ex = conn.execute(
        "SELECT * FROM exams WHERE id=?",
        (exam_id,)
    ).fetchone()

    qs = conn.execute(
        "SELECT * FROM questions WHERE exam_id=?",
        (exam_id,)
    ).fetchall()

    cp = conn.execute(
        """SELECT * FROM checkpoints
           WHERE student_id=? AND exam_id=?
           ORDER BY id DESC LIMIT 1""",
        (session["user_id"], exam_id)
    ).fetchone()

    conn.close()

    if not ex:
        return "Exam not found", 404

    checkpoint = json.loads(cp["answers"]) if cp else {}

    return render_template(
        "exam.html",
        exam=ex,
        questions=qs,
        checkpoint=checkpoint,
        remaining=cp["remaining_time"] if cp else ex["duration"] * 60
    )

@app.post("/api/checkpoint")
@login_required("student")
def checkpoint():
    data = request.get_json()

    conn = db()

    conn.execute(
        """INSERT INTO checkpoints
           (student_id,exam_id,current_question,answers,remaining_time,created_at)
           VALUES(?,?,?,?,?,?)""",
        (
            session["user_id"],
            data["exam_id"],
            data["current_question"],
            json.dumps(data["answers"]),
            data["remaining_time"],
            datetime.now().isoformat()
        )
    )

    conn.commit()
    conn.close()

    return jsonify(
        ok=True,
        message="Checkpoint saved"
    )

@app.post("/api/failure")
@login_required("student")
def failure():
    data = request.get_json()

    conn = db()

    conn.execute(
        """INSERT INTO failure_logs
           (student_id,exam_id,failure_type,rollback_time,action_taken)
           VALUES(?,?,?,?,?)""",
        (
            session["user_id"],
            data["exam_id"],
            data["failure_type"],
            datetime.now().isoformat(),
            "Last checkpoint restored"
        )
    )

    conn.commit()

    cp = conn.execute(
        """SELECT * FROM checkpoints
           WHERE student_id=? AND exam_id=?
           ORDER BY id DESC LIMIT 1""",
        (
            session["user_id"],
            data["exam_id"]
        )
    ).fetchone()

    conn.close()

    if not cp:
        return jsonify(
            ok=False,
            message="No checkpoint available"
        )

    return jsonify(
        ok=True,
        current_question=cp["current_question"],
        answers=json.loads(cp["answers"]),
        remaining_time=cp["remaining_time"]
    )

@app.post("/submit/<int:exam_id>")
@login_required("student")
def submit(exam_id):
    answers = request.form.get("answers", "{}")

    ans = json.loads(answers)

    conn = db()

    qs = conn.execute(
        "SELECT * FROM questions WHERE exam_id=?",
        (exam_id,)
    ).fetchall()

    score = sum(
        1
        for q in qs
        if ans.get(str(q["id"])) is not None
        and int(ans[str(q["id"])]) == q["correct_answer"]
    )

    total = len(qs)

    pct = (score / total * 100) if total else 0

    status = "PASS" if pct >= 40 else "FAIL"

    conn.execute(
        """INSERT INTO results
           (student_id,exam_id,score,total,percentage,status,created_at)
           VALUES(?,?,?,?,?,?,?)""",
        (
            session["user_id"],
            exam_id,
            score,
            total,
            pct,
            status,
            datetime.now().isoformat()
        )
    )

    conn.commit()
    conn.close()

    return render_template(
        "result.html",
        score=score,
        total=total,
        percentage=pct,
        status=status
    )

@app.route("/admin")
@login_required("admin")
def admin_dashboard():
    conn = db()

    stats = {
        "students": conn.execute(
            "SELECT COUNT(*) FROM users WHERE role='student'"
        ).fetchone()[0],

        "exams": conn.execute(
            "SELECT COUNT(*) FROM exams"
        ).fetchone()[0],

        "results": conn.execute(
            "SELECT COUNT(*) FROM results"
        ).fetchone()[0],

        "rollbacks": conn.execute(
            "SELECT COUNT(*) FROM failure_logs"
        ).fetchone()[0]
    }

    conn.close()

    return render_template(
        "admin_dashboard.html",
        stats=stats
    )

@app.route("/admin/exams", methods=["GET", "POST"])
@login_required("admin")
def admin_exams():
    conn = db()

    if request.method == "POST":
        title = request.form["title"]
        duration = int(request.form["duration"])
        question_limit = int(request.form["question_limit"])

        if question_limit < 1:
            conn.close()

            return render_template(
                "create_exam.html",
                exams=[],
                error="Question limit must be at least 1"
            )

        if question_limit > 50:
            conn.close()

            return render_template(
                "create_exam.html",
                exams=[],
                error="Question limit cannot be more than 50"
            )

        conn.execute(
            """INSERT INTO exams
               (title,duration,question_limit,start_time,end_time)
               VALUES(?,?,?,?,?)""",
            (
                title,
                duration,
                question_limit,
                request.form.get("start_time", ""),
                request.form.get("end_time", "")
            )
        )

        conn.commit()

    exams = conn.execute(
        "SELECT * FROM exams ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return render_template(
        "create_exam.html",
        exams=exams
    )

@app.route("/admin/exam/delete/<int:exam_id>", methods=["POST"])
@login_required("admin")
def delete_exam(exam_id):
    conn = db()

    exam = conn.execute(
        "SELECT * FROM exams WHERE id=?",
        (exam_id,)
    ).fetchone()

    if not exam:
        conn.close()
        return "Exam not found", 404

    conn.execute(
        "DELETE FROM answers WHERE exam_id=?",
        (exam_id,)
    )

    conn.execute(
        "DELETE FROM checkpoints WHERE exam_id=?",
        (exam_id,)
    )

    conn.execute(
        "DELETE FROM results WHERE exam_id=?",
        (exam_id,)
    )

    conn.execute(
        "DELETE FROM failure_logs WHERE exam_id=?",
        (exam_id,)
    )

    conn.execute(
        "DELETE FROM questions WHERE exam_id=?",
        (exam_id,)
    )

    conn.execute(
        "DELETE FROM exams WHERE id=?",
        (exam_id,)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("admin_exams"))

@app.route("/admin/questions/<int:exam_id>", methods=["GET", "POST"])
@login_required("admin")
def admin_questions(exam_id):
    conn = db()

    ex = conn.execute(
        "SELECT * FROM exams WHERE id=?",
        (exam_id,)
    ).fetchone()

    if not ex:
        conn.close()
        return "Exam not found", 404

    current_count = conn.execute(
        "SELECT COUNT(*) FROM questions WHERE exam_id=?",
        (exam_id,)
    ).fetchone()[0]

    if request.method == "POST":
        if current_count >= ex["question_limit"]:
            qs = conn.execute(
                "SELECT * FROM questions WHERE exam_id=?",
                (exam_id,)
            ).fetchall()

            conn.close()

            return render_template(
                "add_questions.html",
                exam=ex,
                questions=qs,
                error="Question limit reached"
            )

        conn.execute(
            """INSERT INTO questions
               (exam_id,question,option_a,option_b,option_c,option_d,correct_answer)
               VALUES(?,?,?,?,?,?,?)""",
            (
                exam_id,
                request.form["question"],
                request.form["a"],
                request.form["b"],
                request.form["c"],
                request.form["d"],
                int(request.form["correct"])
            )
        )

        conn.commit()

        current_count += 1

    qs = conn.execute(
        "SELECT * FROM questions WHERE exam_id=?",
        (exam_id,)
    ).fetchall()

    conn.close()

    return render_template(
        "add_questions.html",
        exam=ex,
        questions=qs,
        question_count=current_count
    )

@app.route("/admin/monitoring")
@login_required("admin")
def monitoring():
    conn = db()

    rows = conn.execute(
        """SELECT r.*,u.name,e.title
           FROM results r
           JOIN users u ON u.id=r.student_id
           JOIN exams e ON e.id=r.exam_id
           ORDER BY r.id DESC"""
    ).fetchall()

    conn.close()

    return render_template(
        "monitoring.html",
        rows=rows
    )

@app.route("/admin/failures")
@login_required("admin")
def failures():
    conn = db()

    rows = conn.execute(
        """SELECT f.*,u.name,e.title
           FROM failure_logs f
           JOIN users u ON u.id=f.student_id
           JOIN exams e ON e.id=f.exam_id
           ORDER BY f.id DESC"""
    ).fetchall()

    conn.close()

    return render_template(
        "failure_logs.html",
        rows=rows
    )

if __name__ == "__main__":
    init_db()
    app.run(debug=True)