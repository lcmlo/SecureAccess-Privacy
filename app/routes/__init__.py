def register_blueprints(app):
    from . import admin, auth, organization, privacy, user

    for blueprint in (auth.bp, user.bp, privacy.bp, admin.bp, organization.bp):
        app.register_blueprint(blueprint)
