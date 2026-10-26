import click
from werkzeug.exceptions import BadRequest

from app.services.retention_service import cleanup
from app.services.user_service import promote_admin


def register_commands(app):
    @app.cli.command("cleanup")
    def cleanup_command():
        logs, receipts = cleanup()
        click.echo(f"Eliminados: {logs} registos e {receipts} comprovativos expirados.")

    @app.cli.command("promote-admin")
    @click.argument("username")
    def promote_admin_command(username):
        try:
            promote_admin(username)
        except BadRequest as error:
            raise click.ClickException(error.description) from error
        click.echo("Perfil administrativo atribuído; sessões anteriores revogadas.")
