"""Classes for files and file info."""
import itertools
from collections import namedtuple

import bs4
import re
import requests
import subprocess
from pathlib import Path
import sys
import attr
from fuzzywuzzy import process
from lilyskel.lynames import Instrument, Ensemble
from lilyskel import mutopia
from lilyskel import exceptions
from lilyskel import db_interface

ENCODING = sys.stdout.encoding
KeySignature = namedtuple('KeySignature', ['note', 'mode'])
ALLOWED_NOTES = None
ALLOWED_MODES = None
LANGUAGES = None


@attr.s
class Composer:
    """Stores and formats information about a composer."""
    name = attr.ib(validator=attr.validators.instance_of(str))
    mutopianame = attr.ib(default=None)
    shortname = attr.ib(default=None)

    def get_short_name(self):
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

    def get_mutopia_name(self, guess=False):
        """
        Get the mutopia name for a composer.
        :param guess: if True, a guess will be made at the mutopia name of a
            composer.
        """
        if self.mutopianame is not None:
            return self.mutopianame
        elif guess:
            mutopia_composers = mutopia.get_composers()
            namelist = self.name.split()
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

        :param name: part or all of a composer's name
        :param db: a TinyDB instance
        """
        table = db.table('composers')
        name_parts = name.split(' ')
        lname = name_parts.pop()
        comps = db_interface.explore_table(table=table, search=('name', lname))
        if not isinstance(comps, list):
            comps = [comps]
        for item in comps:
            if name_parts[0] in item:
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

        :param db: a tinydb instance to insert into.
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

    def dump(self):
        return attr.asdict(self)


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

    def add_mutopia_headers(self, mu_headers, guess_composer=False,
                            instruments=None):
        """
        Add mutopia headers.
        :param mu_headers: a MutopiaHeaders object
        :param guess_composer: Whether to guess at the mutopiacomposer if not set.

        Note: This will overwrite the copyright to match the license.
        """
        # pylint: disable=no-member
        mu_headers.composer = self.composer.get_mutopia_name(
            guess=guess_composer)
        # pylint: enable=no-member
        if instruments is None:
            instruments = mu_headers.instrument_list

        # converts list of instruments to mutopia friendly string
        # instruments.sort()
        mutopia_instrument_names =\
            set([instrument.get_mutopia_name() for
             instrument in instruments])
        mutopia_names_list = list(mutopia_instrument_names)
        mutopia_names_list.sort()
        instruments = ', '.join(mutopia_names_list)
        mu_headers.instruments = instruments
        self.copyright = mu_headers.license
        self.mutopiaheaders = mu_headers

    @classmethod
    def load(cls, datadict, instruments=None):
        """Load info from dict."""
        mutopiaheaders = None
        comp = Composer.load(datadict.pop('composer'))
        try:
            if datadict['mutopiaheaders']:
                mutopiaheaders = MutopiaHeaders.load(
                    datadict.pop('mutopiaheaders'))
        except KeyError:
            mutopiaheaders = None
        newheaders = cls(title=datadict.pop('title'), composer=comp)
        for key, value in datadict.items():
            setattr(newheaders, key, value)
        if mutopiaheaders:
            newheaders.add_mutopia_headers(mutopiaheaders,
                                           instruments=instruments)
        return newheaders

    def dump(self):
        """
        Dump to dict for serialization to yaml/json.
        Note: This will also serialize the composer object in the composer
        field.
        """
        return attr.asdict(self)


def convert_ensemble(instruments):
    """Returns list of instruments for mutopia headers."""
    if isinstance(instruments, Ensemble):
        return instruments.instruments
    return instruments


@attr.s
class MutopiaHeaders:
    """
    The headers available for Mutopia project submissions. See www.mutopia.org
    for more details.
    """
    source = attr.ib(validator=attr.validators.instance_of(str))
    style = attr.ib()
    instrument_list = attr.ib(convert=convert_ensemble, default=[])
    license = attr.ib(default='Public Domain')
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
        try:
            if isinstance(value, list):
                if isinstance(value[0], Instrument):
                    return
            raise TypeError("'instruments' must be a list of instruments")
        except IndexError:
            return

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

    @classmethod
    def load(cls, datadict):
        newclass = cls(source=datadict.pop('source'),
                       style=datadict.pop('style'))
        for key, value in datadict.items():
            setattr(newclass, key, value)
        return newclass


def convert_key(keyinfo):
    return KeySignature(keyinfo[0], keyinfo[1])


def get_allowed_notes():
    global ALLOWED_NOTES
    if ALLOWED_NOTES:
        return ALLOWED_NOTES
    docpage = requests.get('http://lilypond.org/doc/v2.18/Documentation/notation/writing-pitches')
    soup = bs4.BeautifulSoup(docpage.text, 'html.parser')
    tables = soup.find_all('table')
    note_name_table = None
    for table in tables:
        if "Note Names" in table.text:
            note_name_table = table
            break
    note_name_p = note_name_table.find_all('p')
    base_note_names = []
    for item in note_name_p:
        item_as_list = item.text.strip().split(' ')
        if len(item_as_list) == 8:
            base_note_names.extend(item_as_list)
    base_note_names = list(set(base_note_names))
    for table in tables:
        if "sharp" in table.text:
            curr_table = table
            break
    note_suffixes_p = curr_table.find_all('p')
    note_suffixes_table = []
    for item in note_suffixes_p:
        if '-' in item.text:
            # print('item found')
            clean = item.text.strip().replace('-', '').split('/')
            note_suffixes_table.extend(clean)
    note_suffixes_table = list(set(note_suffixes_table))
    note_suffixes_table.append('')
    ALLOWED_NOTES = [pair[0] + pair[1] for pair in itertools.product(base_note_names, note_suffixes_table)]
    return ALLOWED_NOTES


def get_allowed_modes():
    global ALLOWED_MODES
    if ALLOWED_MODES:
        return ALLOWED_MODES
    docpage2 = requests.get('http://lilypond.org/doc/v2.18/Documentation/notation/displaying-pitches')
    soup = bs4.BeautifulSoup(docpage2.text, "html.parser")
    all_ps = soup.find_all('p')
    curr_p = None
    for a_p in all_ps:
        if 'mode' in a_p.text and 'key signature' in a_p.text:
            curr_p = a_p
            break
    mode_ps = curr_p.find_all('code')
    ALLOWED_MODES = [item.text.replace('\\', '') for item in mode_ps if '\\' in item.text]
    return ALLOWED_MODES


@attr.s(slots=True)
class Movement:
    num = attr.ib(validator=attr.validators.instance_of(int))
    tempo = attr.ib(validator=attr.validators.instance_of(str),
                    default='')
    time = attr.ib(validator=attr.validators.instance_of(str),
                   default='')
    key = attr.ib(convert=convert_key, default=('c', 'major'))

    @key.validator
    def validate_key(self, attribute, value):
        """Validate key."""
        err = AttributeError("'key' must be tuple of note and major or minor")
        if not isinstance(value, KeySignature):
            raise err
        if value.note not in get_allowed_notes():
            raise err
        if value.mode not in get_allowed_modes():
            raise err

    @classmethod
    def load(cls, datadict):
        newclass = cls(num=datadict.pop('num'), key=datadict.pop('key'))
        for key, value in datadict.items():
            setattr(newclass, key, value)
        return newclass

    def dump(self):
        return attr.asdict(self)


def get_valid_languages():
    global LANGUAGES
    if LANGUAGES:
        return LANGUAGES
    langfile = Path('/usr', 'share', 'lilypond', get_vers(), 'scm',
                    'define-note-names.scm')
    with open(langfile, 'rb') as file_:
        content = file_.read()
    langs = re.findall(r'Language: ([^\s]*)', content.decode(ENCODING),
                       re.M | re.I)
    LANGUAGES = [lang.lower() for lang in langs]
    return LANGUAGES


def get_vers():
    run_ly = subprocess.run(['lilypond', '--version'],
                            stdout=subprocess.PIPE)
    matchvers = re.search(r'LilyPond ([^\n]*)',
                          run_ly.stdout.decode(ENCODING))
    return matchvers.group(1)

@attr.s
class Piece:
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
    def validate_version(self, _attribute, value):
        """Check that the version number makes sense."""
        try:
            assert re.match(r'[0-9]', value)
        except AssertionError:
            raise AttributeError("Lilypond version number does not appear to "
                                 " be valid. Check you installation.")

    @language.validator
    def validate_language(self, _attribute, value):
        """Check for a valid language."""
        if value is None:
            return
        if value.lower() not in get_valid_languages():
            raise AttributeError("Language is not valid. Must be one of "
                                 "{}".format(', '.join(languages)))

    @movements.validator
    def movements_validator(self, _attribute, value):
        """Check for valid movements."""
        err = AttributeError("Movements are not valid, Must be a list of "
                             "Movement objects.")
        if not isinstance(value, list):
            raise err
        if not isinstance(value[0], Movement):
            raise err

    @instruments.validator
    def validate_instrument_list(self, _attribute, value):
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
                     movements=None):
        """Automatically gets the version number from the system."""
        if movements is None:
            movements = [Movement(num=1)]
        return cls(headers=headers, version=get_vers(), language=language,
                   opus=opus, movements=movements, instruments=instruments)

    def dump(self):
        """Serialize internal data for writing to config file."""
        return {
            "headers" : self.headers.dump(),
            "version": self.version,
            "instruments": [attr.asdict(ins) for ins in self.instruments],
            "language": self.language,
            "opus": self.opus,
            "movements": [mov.dump() for mov in self.movements]
        }

    @classmethod
    def load(cls, datadict):
        """Load class from dict."""
        instruments = [Instrument.load(ins)
                       for ins in datadict.pop('instruments')]
        return cls(
            headers=Headers.load(datadict.pop('headers'), instruments),
            version=datadict.pop('version'),
            instruments=instruments,
            opus=datadict.pop('opus'),
            movements=[Movement.load(mov)
                       for mov in datadict.pop('movements')],
            language=datadict.pop('language')
        )
