import os

import feedparser

from sqlalchemy import Column, Integer, Boolean, String, ForeignKey, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from datetime import datetime, timedelta

from dateutil import parser

from dotenv import load_dotenv


# Export .env file.
load_dotenv('.env')

# Set up DB.
engine = create_engine(os.getenv("DB_URI"))

Session = sessionmaker(bind=engine)
session = Session()

Base = declarative_base(bind=engine)


class Author(Base):
    """
    Represents an author or account on Substack users follow.
    """

    __tablename__ = "authors"

    # Attributes:
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    subdomain = Column(String, unique=True, nullable=False)
    thumbnail = Column(String, nullable=False)

    def __init__(self, subdomain=None, **kwargs):
        """
        Check the author can be found before saving to DB.
        """
        super(Author, self).__init__(**kwargs)

        self.subdomain = subdomain

        # Check the subdomain is valid.
        xml_feed = self._xml_feed().feed
        if not "title" in xml_feed:
            raise ValueError(
                f"Unable to find author '{subdomain}' on Substack."
                f" Are you sure this is a subdomain?"
            )

        self.username = xml_feed["copyright"]
        self.thumbnail = xml_feed["image"]["href"]

        session.add(self)
        session.commit()

    def _xml_feed(self):
        """
        Return link to authors XML feed.
        """
        return feedparser.parse(f"http://{self.subdomain}.substack.com/feed")

    def page_url(self):
        return f"https://{self.subdomain}.substack.com"

    def update_articles(self):
        """
        Return a list of the Author's articles.
        """
        entries = self._xml_feed()["entries"]

        # Extract only articles from feed.
        is_article = lambda a: a["published"] and a["title"] != "Coming soon"
        articles_list = list(filter(is_article, entries))

        # Save all new articles into DB.
        for a in articles_list:

            # Only save Articles from within preferred time frame.
            published_date = parser.parse(a["published"]).replace(tzinfo=None)
            posted_delta = datetime.now() - published_date

            if posted_delta.days > int(os.getenv("OLDEST_POST_DELTA")):
                continue

            # Check its not in the DB already.
            q = session.query(Article).filter(Article.title == a["title"]).first()
            if q is not None:
                continue

            args = {
                "title": a["title"],
                "url": a["links"][0]["href"],
                "published": a["published"],
                "author_id": self.id,
            }

            article = Article(**args)


class Article(Base):
    """
    Represents an article posted by an Author.
    """

    __tablename__ = "articles"

    # Attributes:
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    url = Column(String, nullable=False)
    published = Column(String, nullable=False)
    posted = Column(Boolean)
    author_id = Column(Integer, ForeignKey("authors.id"))

    def __init__(self, title, url, published, author_id, **kwargs):
        """
        Check the author can be found before saving to DB.
        """
        super(Article, self).__init__(**kwargs)
        
        self.title = title
        self.url = url
        self.published = published
        self.author_id = author_id
        self.posted = False

        session.add(self)
        session.commit()

    def get_author(self):
        """
        Use Foreign Key to fetch Author of Article.
        """
        return session.query(Author).filter(Author.id == self.author_id).first()


if __name__ == "__main__":
    # Run seperately to set up tables.
    Base.metadata.create_all()
