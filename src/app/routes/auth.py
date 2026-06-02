from flask import Blueprint, redirect, render_template, request, session, url_for

from src.config import settings

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if settings.admin_password and request.form.get("password", "") == settings.admin_password:
            session["authenticated"] = True
            return redirect(url_for("admin.index"))
        error = "ACCESS_DENIED // INVALID_CREDENTIALS"
    return render_template("login.html", error=error)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
