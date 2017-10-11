"""Classes for files and file info."""
import re
import subprocess
from pathlib import Path
import sys
import attr
from fuzzywuzzy import process
from lilyskel.lynames import Instrument, Ensemble
from lilyskel import mutopia
from lilyskel import exceptions
from lilyskel import db_interface
# pylint: disable=too-few-public-methods,protected-access

ENCODING = sys.stdout.encoding


@attr.s
class Composer():
    """Stores and formats information about a composer."""
    name = attr.ib(validator=attr.validators.instance_of(str))
    mutopianame = attr.ib(default=None)
    shortname = attr.ib(default=None)

    def get_short_name(self):
        # pylint: disable=no-member,unsubscriptable-object
        """Returns shortened composer name. Generates if not present."""
        if self.shortname is not None:
            return self.shortname
        sname = ''
        name_parts = self.name.split()
        lname = name_parts.pop()
        for part in name_parts:
            sname += part[0] + '.'

        # This prevents leading spaces on single name composers
        if sname:
            sname += ' '
        sname += lname
        self.shortname = sname
        return sname

        # pylint: enable=no-member,unsubscriptable-object

    def get_mutopia_name(self, guess=False):
        """
        Get the mutopia name for a composer.
        Arugments:
            guess: if True, a guess will be made at the mutopia name of a
            composer.
        """
        if self.mutopianame is not None:
            return self.mutopianame
        elif guess:
            mutopia_composers = mutopia._get_composers()
            # pylint: disable=no-member
            namelist = self.name.split()
            # pylint: enable=no-member
            lname = namelist.pop()
            name, _ = process.extractOne(self.name, mutopia_composers)
            if lname not in name:
                raise exceptions.MutopiaError("No matching composer found.")
            self.mutopianame = name
            return name
        else:
            raise AttributeError("No mutopia name defined.")

    @classmethod
    def load_from_db(cls, name, db):
        """
        Loads a composer from the database.

        Arguments:
            name: part or all of a composer's name
            db: a TinyDB instance
        """
        table = db.table('composers')
        name_parts = name.split(' ')
        lname = name_parts.pop()
        comps = db_interface.explore_table(table=table, search=('name', lname))
        if not isinstance(comps, list):
            comps = [comps]
        for item in comps:
            if name_parts[0] in item:
                print(item)
                data = db_interface.load_name_from_table(item, db=db,
                                                         tablename='composers')
                name = data['name']
                try:
                    mutopianame = data['mutopianame']
                except KeyError:
                    mutopianame = None
                try:
                    shortname = data['shortname']
                except KeyError:
                    shortname = None

        return cls(name=name, mutopianame=mutopianame, shortname=shortname)

    def add_to_db(self, db):
        """
        Serializes the Instrument and adds it to the supplied database in the
        'composers' table.
        This should only be called after load_from_db fails or the databse is
        otherwise checked so duplicates aren't added to the database.

        Arguments:
            db: a tinydb instance to insert into.
        """
        comp_table = db.table('composers')
        data = attr.asdict(self)
        comp_table.insert(data)

    @classmethod
    def load(cls, datadict):
        """Load info from dict."""
        newcomp = cls(name=datadict.pop('name'))
        for key, value in datadict.items():
            setattr(newcomp, key, value)
        return newcomp


def _validate_mutopia_headers(headers):
    if headers is not None and not isinstance(headers, MutopiaHeaders):
        raise TypeError("mutopiaheaders is defined but not a MutopiaHeaders"
                        " object.")


@attr.s
class Headers(object):
    """Class for storing header info."""
    title = attr.ib()
    composer = attr.ib(default=Composer('Anonymous'),
                       validator=attr.validators.instance_of(Composer))
    dedication = attr.ib(default=None)
    subtitle = attr.ib(default=None)
    subsubtitle = attr.ib(default=None)
    poet = attr.ib(default=None)
    meter = attr.ib(default=None)
    arranger = attr.ib(default=None)
    tagline = attr.ib(default=None)
    copyright = attr.ib(default=None)
    mutopiaheaders = attr.ib(default=None)

    def add_mutopia_headers(self, mu_headers, guess_composer=False):
        """
        Add mutopia headers.
        Arguments:
            mu_headers: a MutopiaHeaders object
            guess_composer: Whether to guess at the mutopiacomposer if not set.

        Note: This will overwrite the copyright to match the license.
        """
        # pylint: disable=no-member
        mu_headers.composer = self.composer.get_mutopia_name(
            guess=guess_composer)
        # pylint: enable=no-member

        # converts list of instruments to mutopia friendly string
        mutopia_instrument_names =\
            [instrument.get_mutopia_name() for
             instrument in mu_headers.instrument_list]
        instruments = ', '.join(mutopia_instrument_names)
        mu_headers.instruments = instruments
        self.copyright = mu_headers.license
        self.mutopiaheaders = mu_headers

    @classmethod
    def load(cls, datadict):
        """Load info from dict."""
        comp = Composer._load(datadict.pop('composer'))
        try:
            mutopiaheaders = MutopiaHeaders._load(
                datadict.pop('mutopiaheaders'))
        except KeyError:
            mutopiaheaders = None
        newheaders = cls(title=datadict.pop('title'), composer=comp,
                         mutopiaheaders=mutopiaheaders)
        for key, value in datadict.items():
            setattr(newheaders, key, value)
        return newheaders

    def dump(self):
        """Dump to dict for serialization to yaml/json.
        Note: This will also serialize the composer object in the composer
        field.
        """
        return attr.asdict(self)


def convert_ensemble(instruments):
    """Returns list of instruments for mutopia headers."""
    if isinstance(instruments, Ensemble):
        return instruments.instruments
    return instruments


def convert_license(license_):
    """Returns the proper name of the license."""
    licenses = {
        'cc4':  'Creative Commons Attribution 4.0',
        'ccsa4': 'Creative Commons Attribution-ShareAlike 4.0',
        'pd': 'Public Domain'
    }
    return licenses.get(license_)


@attr.s
class MutopiaHeaders():
    """
    The headers available for Mutopia project submissions. See www.mutopia.org
    for more details.
    """
    instrument_list = attr.ib(convert=convert_ensemble)
    source = attr.ib(validator=attr.validators.instance_of(str))
    style = attr.ib()
    license = attr.ib(default='pd', convert=convert_license)
    composer = attr.ib(init=False)
    maintainer = attr.ib(default="Anonymous")
    maintainerEmail = attr.ib(default=None)
    maintainerWeb = attr.ib(default=None)
    mutopiatitle = attr.ib(default=None)
    mutopiapoet = attr.ib(default=None)
    mutopiaopus = attr.ib(default=None)
    date = attr.ib(default=None)
    moreinfo = attr.ib(default=None)
    instruments = attr.ib(init=False,
                          validator=attr.validators.instance_of(str))

    @instrument_list.validator
    def validate_instruments(self, attribute, value):
        """Validates a list of instruments."""
        if isinstance(value, list):
            if isinstance(value[0], Instrument):
                return
        raise TypeError("'instruments' must be a list of instruments")

    @style.validator
    def _validate_style(self, attribute, value):
        """Calls validate_mutopia with field 'style'"""
        mutopia.validate_mutopia(data=value, field='style')

    @composer.validator
    def _validate_composer(self, attribute, value):
        """Calls validate_mutopia with field 'mutopiacomposer'"""
        mutopia.validate_mutopia(data=comp, field='mutopiacomposer')

    @license.validator
    def _validate_license(self, attribute, value):
        """Calls validate_mutopia with field 'license'"""
        mutopia.validate_mutopia(data=value, field='license')


@attr.s(slots=True)
class Movement():
    num = attr.ib(validator=attr.validators.instance_of(int))
    tempo = attr.ib(validator=attr.validators.instance_of(str),
                    default='')
    time = attr.ib(validator=attr.validators.instance_of(str),
                   default='')
    key = attr.ib(default=('c', 'major'))

    @key.validator
    def validate_key(self, attribute, value):
        """Validate key."""
        err = AttributeError("'key' must be tuple of note and major or minor")
        if not isinstance(value, tuple):
            raise err
        if value[0][0] not in ['a', 'b', 'c', 'd', 'e', 'f', 'g']:
            raise err
        try:
            if value[0][1] not in ['f', 'b']:
                raise err
        except IndexError:
            pass

        if value[1] not in ['major', 'minor']:
            raise err


@attr.s
class Piece():
    """
    Info for the entire piece.
    """
    headers = attr.ib(validator=attr.validators.instance_of(Headers))
    version = attr.ib()
    instruments = attr.ib()
    language = attr.ib(default=None)
    opus = attr.ib(default=None)
    movements = attr.ib(default=[Movement(num=1)])

    @version.validator
    def validate_version(self, attribute, value):
        """Check that the version number makes sense."""
        try:
            assert re.match(r'[0-9]', value)
        except AssertionError:
            raise AttributeError("Lilypond version number does not appear to "
                                 " be valid. Check you installation.")

    @language.validator
    def validate_language(self, attribute, value):
        """Check for a valid language."""
        langfile = Path('/usr', 'share', 'lilypond', self.version, 'scm',
                        'define-note-names.scm')
        with open(langfile, 'rb') as file_:
            content = file_.read()
        langs = re.findall(r'Language: ([^\s]*)', content.decode(ENCODING),
                           re.M | re.I)
        languages = [lang.lower() for lang in langs]
        if value.lower() not in languages:
            raise AttributeError("Language is not valid. Must be one of "
                                 "{}".format(', '.join(languages)))

    @movements.validator
    def movements_validator(self, attribute, value):
        """Check for valid movements."""
        err = AttributeError("Movements are not valid, Must be a list of "
                             "Movement objects.")
        if not isinstance(value, list):
            raise err
        if not isinstance(value[0], Movement):
            raise err

    @instruments.validator
    def validate_instrument_list(self, attribute, value):
        if isinstance(value, Ensemble):
            return
        if not isinstance(value, list):
            raise AttributeError(
                'instrument_list must be a list of instruments.')
        if not isinstance(value[0], Instrument):
            raise AttributeError(
                'instrument_list must be a list of instruments.')

    @classmethod
    def init_version(cls, headers, instruments, language=None, opus=None,
                     movements=[Movement(num=1)]):
        """Automatically gets the version number from the system."""
        run_ly = subprocess.run(['lilypond', '--version'],
                                stdout=subprocess.PIPE)
        matchvers = re.search(r'LilyPond ([^\n]*)',
                              run_ly.stdout.decode(ENCODING))
        vers = matchvers.group(1)
        return cls(headers=headers, version=vers, language=language,
                   opus=opus, movements=movements, instruments=instruments)

    def serialize(self):
        """Serialize internal data for writing to config file."""
        data = {}