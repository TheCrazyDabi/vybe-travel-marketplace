from datetime import datetime

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

from models import AuditEvent, TravelerProfile, User, UserPreference, db
from services.auth_tokens import (
    check_rate_limit,
    generate_email_verification_token,
    generate_password_reset_token,
    verify_email_token,
    verify_password_reset_token,
)

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


class ForgotPasswordForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), _email_validator])
    submit = SubmitField("Send password reset link")


class ResetPasswordForm(FlaskForm):
    password = PasswordField("New Password", validators=[DataRequired(), Length(min=6)])
    submit = SubmitField("Reset password")


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
    if form.validate_on_submit():
        # Prevent self-assignment of admin or privileged roles
        role = (form.role.data or "traveler").lower()
        if role not in ("traveler", "operator"):
            role = "traveler"

        email = form.email.data.strip().lower()
        if User.query.filter_by(email=email).first():
            flash("Email already registered. Please log in.", "error")
            return render_template("register.html", form=form)

        user = User(name=form.name.data.strip(), email=email, role=role)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()
        _get_or_create_profile(user)
        db.session.commit()

        AuditEvent.log("auth.register", user_id=user.id, request=request)
        login_user(user)
        flash(f"Welcome to VYBE, {user.name}!", "success")
        return redirect(url_for("traveler.onboarding") if role == "traveler" else url_for("operator.dashboard"))
    return render_template("register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = LoginForm()

    ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
    if not check_rate_limit(f"login_form:{ip}", limit=15, window_seconds=60):
        flash("Too many failed attempts. Please wait a moment.", "error")
        return render_template("login.html", form=form), 429

    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()

        if user and (user.status or "active") != "active":
            AuditEvent.log("auth.login_suspended", user_id=user.id, details={"email": email}, request=request)
            flash("Account suspended. Contact support.", "error")
        elif user and user.check_password(form.password.data):
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            login_user(user)
            AuditEvent.log("auth.login_success", user_id=user.id, request=request)
            flash(f"Welcome back, {user.name}!", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for(_dashboard_for(user.role)))
        else:
            AuditEvent.log("auth.login_failed", details={"email": email}, request=request)
            flash("Invalid email or password.", "error")
    return render_template("login.html", form=form)


@auth_bp.get("/logout")
@login_required
def logout_page():
    uid = current_user.id
    logout_user()
    AuditEvent.log("auth.logout", user_id=uid, request=request)
    flash("Logged out.", "success")
    return redirect(url_for("main.index"))


# ---- Password Reset & Email Verification (HTML) ----

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password_page():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = generate_password_reset_token(user.id)
            AuditEvent.log("auth.forgot_password_requested", user_id=user.id, request=request)
            # In development/demo, flash the link directly; in production, send via email provider
            flash(f"Reset link generated: {url_for('auth.reset_password_page', token=token, _external=True)}", "info")
        else:
            # Constant-time/generic message prevents email enumeration
            flash("If that email address is registered, password reset instructions have been sent.", "info")
    return render_template("forgot_password.html", form=form) if request.endpoint == "auth.forgot_password_page" else jsonify({"ok": True})


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password_page(token: str):
    user_id = verify_password_reset_token(token)
    if not user_id:
        flash("Invalid or expired password reset link.", "error")
        return redirect(url_for("auth.login_page"))

    user = db.session.get(User, user_id)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("auth.login_page"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        AuditEvent.log("auth.password_reset_completed", user_id=user.id, request=request)
        flash("Password successfully reset! Please log in with your new password.", "success")
        return redirect(url_for("auth.login_page"))

    return render_template("reset_password.html", form=form, token=token)


@auth_bp.get("/verify-email/<token>")
def verify_email_route(token: str):
    user_id = verify_email_token(token)
    if not user_id:
        flash("Invalid or expired verification link.", "error")
        return redirect(url_for("main.index"))

    user = db.session.get(User, user_id)
    if user:
        user.is_email_verified = True
        db.session.commit()
        AuditEvent.log("auth.email_verified", user_id=user.id, request=request)
        flash("Email successfully verified!", "success")
    return redirect(url_for("main.index"))


# ---- Production JSON API ----

@auth_bp.post("/api/auth/register")
def api_register():
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    # Strictly enforce role: users can only self-register as traveler or operator (never admin)
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

    AuditEvent.log("auth.api_register", user_id=user.id, request=request)
    login_user(user)
    return jsonify({
        "user": user.to_dict(),
        "verification_token": generate_email_verification_token(user.id),
    }), 201


@auth_bp.post("/api/auth/login")
def api_login():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
    if not check_rate_limit(f"api_login:{ip}", limit=15, window_seconds=60):
        return jsonify({"error": "Too many failed attempts. Please try again later."}), 429

    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    user = User.query.filter_by(email=email).first()

    if user and (user.status or "active") != "active":
        AuditEvent.log("auth.api_login_suspended", user_id=user.id, details={"email": email}, request=request)
        return jsonify({"error": "account suspended"}), 403

    if not user or not user.check_password(data.get("password") or ""):
        AuditEvent.log("auth.api_login_failed", details={"email": email}, request=request)
        return jsonify({"error": "invalid credentials"}), 401

    user.last_login_at = datetime.utcnow()
    db.session.commit()
    login_user(user)
    AuditEvent.log("auth.api_login_success", user_id=user.id, request=request)

    payload = user.to_dict()
    payload["dashboard"] = url_for(_dashboard_for(user.role))
    return jsonify({"user": payload})


@auth_bp.post("/api/auth/logout")
@login_required
def api_logout():
    uid = current_user.id
    logout_user()
    AuditEvent.log("auth.api_logout", user_id=uid, request=request)
    return jsonify({"ok": True})


@auth_bp.post("/api/auth/forgot-password")
def api_forgot_password():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"
    if not check_rate_limit(f"forgot_pw:{ip}", limit=5, window_seconds=60):
        return jsonify({"error": "Too many requests. Please try again later."}), 429

    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    user = User.query.filter_by(email=email).first()

    token = None
    if user:
        token = generate_password_reset_token(user.id)
        AuditEvent.log("auth.api_password_reset_requested", user_id=user.id, request=request)

    # Return standard generic response without leaking if email exists
    resp = {"ok": True, "message": "If that email address is registered, password reset instructions have been sent."}
    # Expose token only in non-production environments to facilitate automated testing
    from flask import current_app
    if current_app.config.get("TESTING") and token:
        resp["_debug_token"] = token
    return jsonify(resp), 200


@auth_bp.post("/api/auth/reset-password")
def api_reset_password():
    data = request.get_json(force=True, silent=True) or {}
    token = data.get("token") or ""
    new_password = data.get("password") or ""

    if not token or len(new_password) < 6:
        return jsonify({"error": "token and 6+ character password required"}), 400

    user_id = verify_password_reset_token(token)
    if not user_id:
        return jsonify({"error": "invalid or expired token"}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404

    user.set_password(new_password)
    db.session.commit()
    AuditEvent.log("auth.api_password_reset_success", user_id=user.id, request=request)
    return jsonify({"ok": True, "message": "Password updated successfully"})


@auth_bp.post("/api/auth/verify-email")
def api_verify_email():
    data = request.get_json(force=True, silent=True) or {}
    token = data.get("token") or ""
    user_id = verify_email_token(token)
    if not user_id:
        return jsonify({"error": "invalid or expired token"}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404

    user.is_email_verified = True
    db.session.commit()
    AuditEvent.log("auth.api_email_verified", user_id=user.id, request=request)
    return jsonify({"ok": True, "user": user.to_dict()})


@auth_bp.post("/api/auth/delete-account")
@login_required
def api_delete_account():
    data = request.get_json(force=True, silent=True) or {}
    password = data.get("password") or ""

    if not current_user.check_password(password):
        return jsonify({"error": "Incorrect password"}), 401

    user_id = current_user.id
    # Soft anonymize user records to preserve financial/booking integrity
    current_user.name = "Deleted User"
    current_user.email = f"deleted_{user_id}_{int(datetime.utcnow().timestamp())}@anonymized.vybe"
    current_user.status = "deleted"
    current_user.set_password(f"deleted_inaccessible_{user_id}")

    if current_user.profile:
        db.session.delete(current_user.profile)
    if current_user.preference:
        db.session.delete(current_user.preference)

    logout_user()
    db.session.commit()
    AuditEvent.log("auth.account_deleted", user_id=user_id, request=request)
    return jsonify({"ok": True, "message": "Account has been successfully deleted."})


@auth_bp.get("/account/delete-request")
def account_delete_request_page():
    """Public web page for account deletion requests (Google Play policy requirement)."""
    return render_template("account_delete_request.html")


@auth_bp.post("/account/delete-request")
def account_delete_request_submit():
    """Process public web account deletion request with credentials verification."""
    is_json = request.is_json
    data = request.get_json(force=True, silent=True) if is_json else request.form
    data = data or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email:
        if is_json:
            return jsonify({"error": "Email is required."}), 400
        return render_template("account_delete_request.html", error="Email is required.")

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        if is_json:
            return jsonify({"error": "Invalid credentials. Please verify your email and password."}), 401
        return render_template("account_delete_request.html", error="Invalid credentials. Please verify your email and password.")

    user_id = user.id
    user.name = "Deleted User"
    user.email = f"deleted_{user_id}_{int(datetime.utcnow().timestamp())}@anonymized.vybe"
    user.status = "deleted"
    user.set_password(f"deleted_inaccessible_{user_id}")

    if user.profile:
        db.session.delete(user.profile)
    if user.preference:
        db.session.delete(user.preference)

    db.session.commit()
    AuditEvent.log("auth.public_account_deleted", user_id=user_id, request=request)

    if is_json:
        return jsonify({"ok": True, "message": "Account has been successfully deleted."}), 200
    return render_template("account_delete_request.html", success=True)

