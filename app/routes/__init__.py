def register_blueprints(app):
    from . import admin, auth, privacy, user

    for blueprint in (auth.bp, user.bp, privacy.bp, admin.bp):
        app.register_blueprint(blueprint)
