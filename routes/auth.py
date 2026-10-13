from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length

try:
    import email_validator  # noqa: F401
    _email_validator = Email()
except ImportError:
    from wtforms.validators import Regexp
    _email_validator = Regexp(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", message="Invalid email address.")

from models import TravelerProfile, User, UserPreference, db

auth_bp = Blueprint("auth", __name__)


class RegisterForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email", validators=[DataRequired(), _email_validator, Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    role = StringField("Role")  # traveler|operator (default traveler)
    submit = SubmitField("Create account")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), _email_validator])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")


def _dashboard_for(role: str) -> str:
    if role == "admin":
        return "admin.dashboard"
    if role == "operator":
        return "operator.dashboard"
    return "traveler.discover"


def _get_or_create_profile(user: User):
    if not user.profile:
        user.profile = TravelerProfile(user_id=user.id)
        db.session.add(user.profile)
    if not user.preference:
        user.preference = UserPreference(user_id=user.id)
        db.session.add(user.preference)
    return user.profile


@auth_bp.route("/register", methods=["GET", "POST"])
def register_page():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = RegisterForm()
    # JSON API clients use /api/auth/register; this page handles HTML forms.
    if form.validate_on_submit():
        role = (form.role.data or "traveler").lower()
        if role not in ("traveler", "operator"):
            role = "traveler"
        if User.query.filter_by(email=form.email.data.lower()).first():
            flash("Email already registered. Please log in.", "error")
            return render_template("register.html", form=form)
        user = User(name=form.name.data, email=form.email.data.lower(), role=role)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()
        _get_or_create_profile(user)
        db.session.commit()
        login_user(user)
        flash(f"Welcome to VYBE, {user.name}!", "success")
        return redirect(url_for("traveler.onboarding") if role == "traveler" else url_for("operator.dashboard"))
    return render_template("register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and (user.status or "active") != "active":
            flash("Account suspended. Contact support.", "error")
        elif user and user.check_password(form.password.data):
            login_user(user)
            flash(f"Welcome back, {user.name}!", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for(_dashboard_for(user.role)))
        else:
            flash("Invalid email or password.", "error")
    return render_template("login.html", form=form)


@auth_bp.get("/logout")
@login_required
def logout_page():
    logout_user()
    flash("Logged out.", "success")
    return redirect(url_for("main.index"))


# ---- JSON API (spec section 14) ----
@auth_bp.post("/api/auth/register")
def api_register():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "traveler").lower()
    if role not in ("traveler", "operator"):
        role = "traveler"
    if not name or not email or len(password) < 6:
        return jsonify({"error": "name, email and 6+ char password required"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "email already registered"}), 409
    user = User(name=name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    _get_or_create_profile(user)
    db.session.commit()
    login_user(user)
    return jsonify({"user": user.to_dict()}), 201


@auth_bp.post("/api/auth/login")
def api_login():
    data = request.get_json(force=True, silent=True) or {}
    user = User.query.filter_by(email=(data.get("email") or "").lower()).first()
    if user and (user.status or "active") != "active":
        return jsonify({"error": "account suspended"}), 403
    if not user or not user.check_password(data.get("password") or ""):
        return jsonify({"error": "invalid credentials"}), 401
    login_user(user)
    payload = user.to_dict()
    payload["dashboard"] = url_for(_dashboard_for(user.role))
    return jsonify({"user": payload})


@auth_bp.post("/api/auth/logout")
@login_required
def api_logout():
    logout_user()
    return jsonify({"ok": True})
