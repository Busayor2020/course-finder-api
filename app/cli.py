import click
from flask import current_app

from app.ingest.pipeline import run_ingestion


@click.command("ingest")
@click.argument("csv_path", type=click.Path(exists=True, dir_okay=False))
def ingest_command(csv_path):
    """Load courses from a CSV file into the database."""
    result = run_ingestion(csv_path, current_app.config["REPORTS_DIR"])
    run = result.run

    click.echo(f"Ingestion run #{run.id}: {run.status} ({run.source_file})")
    for label, value in [
        ("Rows read", run.rows_read),
        ("Inserted", run.inserted),
        ("Updated", run.updated),
        ("Unchanged", run.unchanged),
        ("Rejected", run.rejected),
    ]:
        click.echo(f"  {label:<10} {value:>5}")
    if result.report_path:
        click.echo(f"Rejected rows and reasons: {result.report_path}")
