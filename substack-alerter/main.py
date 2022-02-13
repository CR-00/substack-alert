import os
import re
import sqlite3
import itertools
import traceback

import feedparser

import discord
from discord.ext import tasks

from dotenv import load_dotenv

# Load OAuth credentials from .env file.
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Config:
DB_FILE = "substack.db"


class DB:
    """
    Class to abstract sqlite3 database functions used to handle
    CRUD operations on subscriptions.
    """

    def __init__(self):
        """
        Try to establish a connection, and set up tables if they don't exist.
        """
        try:
            self.conn = sqlite3.connect(DB_FILE)
            self.cursor = self.conn.cursor()
        except sqlite3.Error as e:
            print(f"Error connecting to database: {traceback.format_exc()}")

        try:
            self._create_tables_if_not_exist()
        except sqlite3.Error as e:
            print(f"Unable to set up tables: {traceback.format_exc()}")

    def __enter__(self):
        """
        Enable context managed usage.
        """
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        """
        Close the database connection when object is destroyed.
        """
        self._close()

    def _close(self):
        """
        Internal method to shut the DB down when object is destroyed.
        """
        if self.conn:
            self.conn.commit()
            self.cursor.close()
            self.conn.close()

    def _create_tables_if_not_exist(self):
        """
        Create Authors and Articles tables if they do not exist.
        """
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS authors(
                    authorid INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    UNIQUE(username)
            );
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS articles(
                    articleid INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    posted BOOLEAN NOT NULL CHECK (posted IN (0, 1)),
                    author TEXT NOT NULL,
                    FOREIGN KEY(author) REFERENCES authors(authorid)
            );
            """
        )
        self.conn.commit()

    def add_subscription(self, username):
        self.cursor.execute("INSERT INTO authors VALUES (?,?)", (None, username))

    def remove_subscription(self, username):
        self.cursor.execute("DELETE FROM authors WHERE username = (?)", (username))

    def author_list(self):
        """
        Return the username of every author we have subscribed to.
        Sqlite3 returns tuple of each record by default, so converts this
        into a list.
        """
        authors = self.cursor.execute("SELECT username FROM authors").fetchall()
        return [a[0] for a in authors]

    def get_author_id_from_username(self, username):
        """
        Used to get authorid from a username, NB username is a unique value.
        """
        self.cursor.execute(
            "SELECT authorid FROM authors WHERE username = (?)", (username,)
        )
        return self.cursor.fetchall()[0]

    def add_article(self, title, url, posted, author):
        author_id = self.get_author_id_from_username(author)[0]
        self.cursor.execute(
            "INSERT INTO articles VALUES (?,?,?,?,?)",
            (None, title, url, posted, author_id),
        )

    def set_article_as_posted(title):
        """
        Set boolean variable for an article to True so that it will not
        be posted the next time the bot queries substack.
        """
        self.cursor.execute("UPDATE articles SET posted = 1 WHERE title = (?)", (title))

    def check_article_is_saved(self, title):
        """
        Return True if article is in the DB, else False.
        """
        self.cursor.execute("SELECT title FROM articles WHERE title = (?)", (title,))
        return bool(len(self.cursor.fetchall()))

    def get_articles_list(self):
        """
        Return all articles, may have to change this down the line not that scalable really.
        """
        articles = self.cursor.execute("SELECT * FROM articles").fetchall()
        return articles


# ** Requests **


def is_article(article):
    """
    Used to check an XML entry on the feed is a valid article.
    """
    return article["published"] and article["title"] != "Coming soon"


def get_articles_from_author(author):
    """
    Get the titles from everything on the first page of an author,
    return relevant information.
    """
    ret = []

    entries = feedparser.parse(f"http://{author}.substack.com/feed")["entries"]
    articles = list(filter(is_article, entries))

    for article in articles:

        a = {
            "title": article["title"],
            "url": article["links"][0]["href"],
            "posted": 0,
            "author": article["link"][8:].split('.')[0],
        }
        ret.append(a)
    return ret


# ** Discord Functions **


class SubstackBot(discord.Client):
    """
    Bot handles adding and removing posts and runs a job every 5 minutes
    to see if there are any new articles from the authors in the DB.
    """
    async def on_ready(self):
        print(f"{self.user} has connected to Discord!")

    async def on_message(self, message):
        """
        Handle CRUD operations on subscriptions to authors.
        """
        command = message.content.split(" ")

        # Add subscription.
        if command[0] == "!subscribe":
            username = command[1]
            with DB() as db:
                db.add_subscription(username)
            msg = f"Subscribed to {username}."
            await message.channel.send(msg)

        # Remove subscription.
        if comand[0] == "!unsubscribe":
            username = command[1]
            with DB() as db:
                db.remove_subscription(username)
            msg = f"Unsubscribed from {username}."
            await message.channel.send(msg)

    @tasks.loop(minutes=15)
    async def update_articles(self):
        """
        Every 15 minutes, check every single substack we subscribe
        to for new posts.
        """
        with DB() as db:
            # Get list of all authors, then parse all articles.
            authors = db.author_list()
            articles = [get_articles_from_author(a) for a in authors]

            # If article title not found in DB, save it.
            for article in articles:
                if not db.check_article_is_saved:
                    db.add_article(**article)

    @tasks.loop(minutes=15)
    async def update_articles(self):
        """
        Every 15 minutes, search the articles list and post anything unposted.
        """
        with DB() as db:
            # Get a list of unposted articles.
            articles = db.get_articles_list()
            unposted = filter(lambda x: not x[3])

            for article in filter(unposted, articles):
                msg = (
                    f"@everyone\n"
                    f"New article from {article[4]}\n"
                    f"Title: {article[1]}\n"
                    f"Link: {article[2]}"
                )
                await message.channel.send(msg)


if __name__ == "__main__":
    # Connect to discord.
    substack_bot = SubstackBot()
    substack_bot.run(TOKEN)
