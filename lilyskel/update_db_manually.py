from pathlib import Path
import better_exceptions
import click
from tinydb import TinyDB
from lilyskel.lynames import Instrument
from lilyskel.info import Composer
from lilyskel.exceptions import MutopiaError
from lilyskel import db_interface


db = TinyDB(Path("/home/rick/repositories/lilyskel/lilyskel/default_db.json"))

@click.group()
def cli():
    pass


@cli.command()
def instrument():
    name = input("Instrument Name (lower): ")
    abbr = input("Instrument Abbreviation: ")
    clef = input("Instrument clef: ") or "treble"
    if ' ' in clef:
        clef = clef.split()
    transposition = input("Transposition: ") or None
    keyboard = bool(input("Keyboard? ")) or False
    midi = input("Midi instrument name: ")
    family = input("Instrument family: ")
    mutopianame = input("Mutopia name: ") or None
    new_ins = Instrument(
        name=name,
        abbr=abbr,
        clef=clef,
        transposition=transposition,
        keyboard=keyboard,
        midi=midi,
        family=family,
        mutopianame=mutopianame
    )
    print(new_ins)
    add = input("Correct? [y/N] ")
    if add[0].lower() == 'y':
        new_ins.add_to_db(db)
    return


@cli.command()
@click.argument("name", required=True)
def composer(name):
    # name = input("Composer full name: ")
    newcomp = Composer(name)
    try:
        mutopianame = input(
            f"Assumed Mutopia Name is {newcomp.get_mutopia_name(guess=True)}"
            " Is this correct? [Y/n] "
        ) or "Y"
        if mutopianame[0].lower() == 'n':
            newcomp.mutopianame = input("Enter correct Mutopia Name: ")
    except MutopiaError:
        newcomp.mutopianame = input("Enter correct Mutopia Name: ")
    shortname = input(f"Assumed short name is {newcomp.get_short_name()}"
                      " Correct? [Y/n] ") or "Y"
    if shortname[0].lower() == 'n':
        newcomp.shortname = input("Enter correct short name: ")
    newcomp.add_to_db(db)
    newrec = db_interface.explore_table(
        db.table("composers"), search=("shortname", newcomp.shortname))
    print(newrec)


@cli.command()
@click.argument("name", required=True)
def table(name):
    db.table(name)
    print(name in db.tables() or "Failed")


@cli.command()
@click.argument("table")
@click.argument("infile")
def add_from_file(table, infile):
    """
    Adds data to a table from the lines of a file
    :param table:
    :param infile:
    :return:
    """
    with open(infile, "r") as data:
        items = data.readlines()

    table_obj = db.table(table)
    for item in items:
        table_obj.insert({"word": item})
        print(db_interface.explore_table(table_obj, search=("word", item)))



@cli.command()
@click.argument("table", required=True)
@click.argument("field", required=True)
@click.argument("term", required=True)
def search(table, field, term):
    print(db_interface.explore_table(db.table(table), search=(field, term)))


if __name__ == '__main__':
    cli()
