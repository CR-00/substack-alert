import os

from datetime import datetime

import discord
from discord.ext import tasks, commands

from sqlalchemy.sql.expression import false
from sqlalchemy.exc import IntegrityError, PendingRollbackError

from dotenv import load_dotenv

from models import Author, Article, BannedUser, session

from embeds import help_message, new_article_message

# Export .env file.
load_dotenv(".env")


class SubstackBot(discord.Client):
    """
    Bot handles adding and removing posts and runs a job every 5 minutes
    to see if there are any new articles from the authors in the DB.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def on_ready(self):
        """
        Run startup tasks when job has connected to Discord.
        """
        self.console_log(f"Logged in as {super().user.name}.")

        # Fetch main channel.
        self.channel_id = super().get_channel(int(os.getenv("CHANNEL_ID")))
        self.console_log("Connected to channel.")

        # Schedule jobs.
        self.update_articles.start()
        self.post_articles.start()
        self.console_log("Jobs scheduled.")

    async def on_message(self, message):
        """
        Handle commands from users. Return after each command to prevent
        fallthrough.
        """
        cmd = message.content.split(" ")

        # Try to parse requested Substack subdomain.
        try:
            subdomain = cmd[1]
        except IndexError:
            subdomain = None

        # Post commands list.
        if cmd[0] == "!help":
            return await message.channel.send(embed=help_message())

        # Get list of all authors subscribed to.
        if cmd[0] == "!list":

            subs = [(a.username, a.subdomain) for a in session.query(Author).all()]

            msg = f"Subscriptions:{os.linesep}"
            for sub in subs:
                msg += f"{sub[0]} // {sub[1]}{os.linesep}"

            return await message.channel.send(msg)

        # Don't allow banned users past this point.
        ban_list = [usr.discord_username for usr in session.query(BannedUser).all()]
        if message.author in ban_list:
            return await message.channel.send("Command is off limits to banned users.")

        # Add subscription.
        if cmd[0] == "!subscribe":

            # Badly formed arguments.
            if subdomain is None:
                msg = (
                    "Please enter an author to subscribe to."
                    " Alternatively, use !help for help."
                )
                self.console_log(
                    f"{message.author} !subscribe {subdomain} - BADLY FORMED ARGUMENT"
                )

            else:
                # Try to add the subscription.
                try:
                    a = Author(subdomain)
                    msg = f"Subscribed to {a.username}."
                    self.console_log(
                        f"{message.author} !subscribe {subdomain} - SUCCESS"
                    )

                # Author already in DB.
                except IntegrityError as e:
                    q = (
                        session.query(Author)
                        .filter(Author.subdomain == subdomain)
                        .first()
                    )
                    msg = f"Already subscribed to {q.username}."
                    self.console_log(
                        f"{message.author} !subscribe {subdomain} - INTEGRITY ERROR"
                    )

                # Author constructor raises ValueError if not a real author on Substack.
                except ValueError as e:
                    msg = str(e)
                    # User requested an author that didn't exist, set timeout.
                    if "Unable to find author" in msg:
                        self.console_log(
                            f"{message.author} !subscribe {subdomain} - BAD REQUEST"
                        )

                # Something went wrong.
                except Exception as e:
                    msg = str(e)
                    self.console_log(f"{message.author} !subscribe {subdomain} - ERROR")

            return await message.channel.send(msg)

        # Remove subscription.
        if cmd[0] == "!unsubscribe":

            # Badly formed arguments.
            if subdomain is None:
                msg = (
                    "Please enter an author to unsubcribe from."
                    " Alternatively, use !help for help."
                )
                self.console_log(
                    f"{message.author} !subscribe {subdomain} - BADLY FORMED ARGUMENT"
                )
            else:
                # Try to remove the subscription.
                try:
                    q = session.query(Author).filter(Author.subdomain == cmd[1])
                    a = q.first()

                    if a is not None:
                        session.delete(a)
                        session.commit()
                        msg = f"Unsubscribed from {a.username}."
                        self.console_log(
                            f"{message.author} !unsubscribe {a.subdomain} - SUCCESS"
                        )
                    else:
                        msg = f"No subscription to '{cmd[1]}' found."
                        self.console_log(
                            f"{message.author} !unsubscribe {subdomain} - BAD REQUEST"
                        )

                # Couldn't find author on Substack.
                except ValueError as e:
                    msg = str(e)
                    # User requested an author that didn't exist, set timeout.
                    if "Unable to find author" in msg:
                        self.console_log(
                            f"{message.author} !subscribe {subdomain} - BAD REQUEST"
                        )

                # Something went wrong.
                except Exception as e:
                    msg = str(e)
                    self.console_log(
                        f"{message.author} !unsubscribe {subdomain} - ERROR"
                    )

            return await message.channel.send(msg)

        # Require owner for these commands:
        caller_is_owner = str(message.author) == os.getenv("BOT_OWNER")

        # Add user to banlist.
        if cmd[0] == "!ban" and caller_is_owner:

            # Badly formed argument.
            if len(cmd) < 1:
                msg = "Enter Discord username to ban."
                self.console_log(f"{message.author}: !ban - BAD REQUEST")
            else:
                try:
                    usr = BannedUser(cmd[1])
                    msg = f"Added {cmd[1]} to list of banned users."
                    self.console_log(f"{message.author}: !ban {cmd[1]} - SUCCESS")
                except IntegrityError as e:
                    msg = f"{cmd[1]} is already banned."
                    self.console_log(
                        f"{message.author}: !ban {cmd[1]} - INTEGRITY ERROR"
                    )

            return await message.channel.send(msg)

        # Remove user from banlist.
        if cmd[0] == "!unban" and caller_is_owner:

            # Badly formed argument.
            if len(cmd) < 1:
                msg = "Enter Discord username to unban."
                self.console_log(f"{message.author}: !unban - BAD REQUEST")
            else:
                q = (
                    session.query(BannedUser)
                    .filter(BannedUser.discord_username == cmd[1])
                    .first()
                )

                # User wasn't banned.
                if q is None:
                    msg = f"{cmd[1]} is not banned."
                    self.console_log(f"{message.author}: !ban {cmd[1]} - BAD REQUEST")
                else:
                    session.delete(q)
                    session.commit()
                    msg = f"Removed {cmd[1]} from list of unbanned users."
                    self.console_log(f"{message.author}: !ban {cmd[1]} - SUCCESS")

            return await message.channel.send(msg)

        # Let the bots owner remotely kill the process.
        if cmd[0] == "!exit" and caller_is_owner:
            self.console_log(f"{message.author} !exit")
            exit()

    @tasks.loop(minutes=int(os.getenv("REFRESH_INTERVAL")))
    async def update_articles(self):
        """
        Fetch new Articles for every subscribed to Author.
        """
        self.console_log(f"Fetching new articles.")
        authors = session.query(Author).all()
        for author in authors:
            author.update_articles()

    @tasks.loop(minutes=int(os.getenv("POST_INTERVAL")))
    async def post_articles(self):
        """
        Post all articles with "posted" set to False, then set to True.
        """
        self.console_log(f"Posting new articles.")
        articles = session.query(Article).filter(Article.posted == false()).all()

        for article in articles:

            # Use FK to find Author.
            author = article.get_author()

            # Remove time from full date time string.
            published = "".join(article.published.split(" ")[:-2])

            article_data = {
                "author": author.username,
                "title": article.title,
                "article_url": article.url,
                "thumbnail_url": author.thumbnail,
                "published": published,
            }

            await self.channel_id.send(embed=new_article_message(**article_data))
            self.console_log(
                f"Posted new article '{article.title}' by {author.username}."
            )

            article.posted = True
            session.commit()

    @classmethod
    def console_log(cls, msg):
        """
        Utility method for printing formatted log messages.
        """
        date_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        print(f"{date_time}: {msg}")


if __name__ == "__main__":
    # Connect to discord.
    substack_bot = SubstackBot()
    substack_bot.run(os.getenv("DISCORD_TOKEN"))
