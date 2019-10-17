from __future__ import absolute_import
import binascii

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    Binary,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class Song(Base):
    __tablename__ = "songs"

    id = Column(Integer, primary_key=True, nullable=False)
    name = Column(String(length=255), nullable=False)
    fingerprinted = Column(Boolean, default=False)
    file_sha1 = Column(Binary(length=20), nullable=False)
    hashes = Column(Integer, nullable=False, default=0)


class Fingerprint(Base):
    __tablename__ = "fingerprints"

    id = Column(Integer, primary_key=True, nullable=False)
    hash = Column(Binary(length=10), nullable=False)
    song_id = Column(Integer, ForeignKey(Song.id, ondelete="CASCADE"), nullable=False)
    offset = Column(Integer, nullable=False)

    unique = UniqueConstraint("hash", "song_id", "offset")


class Database(object):
    def __init__(self, url):
        super(Database, self).__init__()
        self.url = url
        self.engine = create_engine(url)
        self.session = sessionmaker(bind=self.engine)()
        Base.metadata.create_all(self.engine)

        # clean by deleting not fully fingerprinted songs; possibly because of abruptly killed previous run
        self.session.query(Song).filter(Song.fingerprinted.is_(False)).delete()
        self.session.commit()

    def set_song_fingerprinted(self, sid):
        """
        Marks a song as having all fingerprints in the database.

        :param sid: Song identifier
        """
        song = self.session.query(Song).filter(Song.id == sid).one()
        song.fingerprinted = True
        self.session.commit()

    def get_songs(self):
        """Returns all fully fingerprinted songs in the database."""
        return self.session.query(Song).filter(Song.fingerprinted)

    def get_song_by_id(self, sid):
        """
        Return a song by its identifier

        :param sid: Song identifier
        """
        return self.session.query(Song).filter(Song.id == sid).one_or_none()

    def insert_song(self, song_name, file_hash):
        """
        Inserts a song name into the database, returns the new
        identifier of the song.

        :param song_name: name of the song
        :param file_hash: sha1 hex digest of the filename
        """
        song = Song(name=song_name, file_sha1=binascii.unhexlify(file_hash))
        self.session.add(song)
        self.session.commit()
        return song.id

    def insert_hashes(self, sid, hashes):
        """
        Insert a multitude of fingerprints.

        :param sid: Song identifier the fingerprints belong to
        :param hashes: A sequence of tuples in the format (hash, offset)
            hash: Part of a sha1 hash, in hexadecimal format
            offset: Offset this hash was created from/at.
        """
        fingerprints = []
        for hash, offset in set(hashes):
            fingerprints.append(
                Fingerprint(
                    hash=binascii.unhexlify(hash), song_id=sid, offset=int(offset)
                )
            )

        self.session.bulk_save_objects(fingerprints)
        song = self.session.query(Song).filter_by(id=sid).first()
        song.hashes = len(fingerprints)
        self.session.commit()

    def return_matches(self, hashes):
        """
        Searches the database for pairs of (hash, offset) values.

        :param hashes: A sequence of tuples in the format (hash, offset)
            hash: Part of a sha1 hash, in hexadecimal format
            offset: Offset this hash was created from/at.

        :returns: a sequence of (sid, offset_difference) tuples.\
            sid: Song identifier
            offset_difference: (offset - database_offset)
        """
        # Create a dictionary of hash => offset pairs for later lookups
        mapper = {}
        for hash, offset in hashes:
            mapper[hash.upper()] = offset

        # Get an iterable of all the hashes we need
        values = [binascii.unhexlify(h) for h in mapper.keys()]

        for fingerprint in self.session.query(Fingerprint).filter(
            Fingerprint.hash.in_(values)
        ):
            hash = binascii.hexlify(fingerprint.hash).upper().decode("utf-8")
            yield (fingerprint.song_id, fingerprint.offset - mapper[hash])
