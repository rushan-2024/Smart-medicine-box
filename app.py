from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
import random
import string
import os

from models import db, User, MedBoxCode, MedBox, Medicine

# ----- App setup -----
app = Flask(__name__)
app.config["SECRET_KEY"] = "change_this_secret_in_production"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///users.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# create DB if not exists
with app.app_context():
    db.create_all()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ----- Utilities -----
def generate_code(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choices(alphabet, k=length))
        if not MedBoxCode.query.filter_by(code=code).first():
            return code


# ----- Routes -----
@app.route("/")
def home():
    return render_template("home.html")


# Signup
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "").strip().lower()

        if not username or not password or role not in ("doctor", "other"):
            flash("Please fill in all fields correctly.", "danger")
            return redirect(url_for("signup"))

        if User.query.filter_by(username=username).first():
            flash("Username already taken.", "danger")
            return redirect(url_for("signup"))

        hashed = generate_password_hash(password)
        u = User(username=username, password=hashed, role=role)
        db.session.add(u)
        db.session.commit()

        flash("Signup successful — please log in.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")


# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash(f"Welcome, {user.username}!", "success")
            return redirect(url_for("home"))
        else:
            flash("Invalid credentials.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html")


# Logout
@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out", "info")
    return redirect(url_for("home"))


# Medicare page
@app.route("/medicare", methods=["GET", "POST"])
@login_required
def medicare():
    message = None

    # Doctor creating a new code/medbox via generate form
    if request.method == "POST" and "create_box" in request.form:
        if current_user.role != "doctor":
            flash("Only doctors can create MedBoxes.", "danger")
            return redirect(url_for("medicare"))
        box_name = request.form.get("box_name", "").strip() or "MedBox"
        code = generate_code(6)
        code_record = MedBoxCode(code=code, name=box_name, created_by=current_user.id)
        db.session.add(code_record)
        db.session.commit()

        # create the medbox tied to the code
        medbox = MedBox(code_id=code_record.id)
        db.session.add(medbox)
        db.session.commit()

        flash(f"MedBox '{box_name}' created with code: {code}", "success")
        return redirect(url_for("medicare"))

    # Joining an existing medbox via code
    if request.method == "POST" and "join_box" in request.form:
        code_entered = request.form.get("box_code", "").strip()
        if not code_entered:
            flash("Enter a code to join a MedBox.", "danger")
            return redirect(url_for("medicare"))

        code_obj = MedBoxCode.query.filter_by(code=code_entered).first()
        if not code_obj:
            flash("Invalid code. Ask a Doctor for the correct code.", "danger")
            return redirect(url_for("medicare"))

        # redirect to medbox view
        return redirect(url_for("medbox", code=code_entered))

    # Show list of codes (doctors see their created codes; others see nothing)
    if current_user.role == "doctor":
        codes = MedBoxCode.query.filter_by(created_by=current_user.id).all()
    else:
        codes = []

    return render_template("medicare.html", codes=codes)


# Medbox page (access by code)
@app.route("/medbox/<code>", methods=["GET", "POST"])
@login_required
def medbox(code):
    code_obj = MedBoxCode.query.filter_by(code=code).first()
    if not code_obj:
        flash("MedBox code not found.", "danger")
        return redirect(url_for("medicare"))

    # fetch medbox tied to that code
    medbox = MedBox.query.filter_by(code_id=code_obj.id).first()
    if not medbox:
        flash("MedBox not available.", "danger")
        return redirect(url_for("medicare"))

    # Doctor (owner) can rename and add medicines
    if request.method == "POST":
        if current_user.role != "doctor" or code_obj.created_by != current_user.id:
            flash("Only the Doctor who created this MedBox can modify it.", "danger")
            return redirect(url_for("medbox", code=code))

        # rename
        if "rename" in request.form:
            new_name = request.form.get("new_name", "").strip()
            if new_name:
                code_obj.name = new_name
                db.session.commit()
                flash("MedBox renamed", "success")
            return redirect(url_for("medbox", code=code))

        # add medicine
        if "add_medicine" in request.form:
            med_name = request.form.get("med_name", "").strip()
            med_time = request.form.get("med_time", "").strip()  # "HH:MM"
            if not med_name or not med_time:
                flash("Provide medicine name and time.", "danger")
                return redirect(url_for("medbox", code=code))

            # validate HH:MM roughly
            if len(med_time) != 5 or med_time[2] != ":":
                flash("Time must be in HH:MM format.", "danger")
                return redirect(url_for("medbox", code=code))

            new_med = Medicine(medbox_id=medbox.id, name=med_name, time=med_time)
            db.session.add(new_med)
            db.session.commit()

            # (optional) Logging for RTC integration — devices will query the API
            app.logger.info(f"Added medicine '{med_name}' at {med_time} to MedBox {code}")

            flash("Medicine added", "success")
            return redirect(url_for("medbox", code=code))

    medicines = Medicine.query.filter_by(medbox_id=medbox.id).order_by(Medicine.time).all()
    return render_template("medbox.html", code_obj=code_obj, medbox=medbox, medicines=medicines)


# API endpoint for RTC / IoT devices
@app.route("/api/medbox/<code>/medicines", methods=["GET"])
def api_get_medicines(code):
    code_obj = MedBoxCode.query.filter_by(code=code).first_or_404()
    medbox = MedBox.query.filter_by(code_id=code_obj.id).first_or_404()
    meds = Medicine.query.filter_by(medbox_id=medbox.id).all()

    data = [{"name": m.name, "time": m.time} for m in meds]
    return jsonify({"medbox": code_obj.name or "MedBox", "code": code_obj.code, "medicines": data})


# ----- run -----
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

