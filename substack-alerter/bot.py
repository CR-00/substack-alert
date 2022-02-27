import os

import discord
from discord.ext import tasks, commands

from sqlalchemy.sql.expression import false
from sqlalchemy.exc import IntegrityError

from dotenv import load_dotenv

from models import Author, Article, session

from embeds import help_message, new_article_message

# Export .env file.
load_dotenv('.env')


class SubstackBot(discord.Client):
    """
    Bot handles adding and removing posts and runs a job every 5 minutes
    to see if there are any new articles from the authors in the DB.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Schedule Jobs.
        self.update_articles.start()
        self.post_articles.start()

    async def on_message(self, message):
        """
        Handle commands from users.
        """
        command = message.content.split(" ")

        # Post commands list.
        if command[0] == "!help":
            await message.channel.send(embed=help_message())
        
        # Add subscription.
        if command[0] == "!subscribe":
            try:
                a = Author(subdomain=command[1])
                msg = f"Subscribed to {a.username}."
            except IndexError:
                msg = (
                    "Please enter an author to subscribe to."
                    " Alternatively, use !help for help."
                )

            except IntegrityError as e:
                msg = f"Already subscribed to {command[1]}."
            except ValueError as e:
                msg = e
            except Exception as e:
                msg = e

            await message.channel.send(msg)

        # Remove subscription.
        if command[0] == "!unsubscribe":
            try:
                q = session.query(Author).filter(Author.subdomain == command[1])
                a = q.first()

                if a is not None:
                    session.delete(a)
                    session.commit()
                    msg = f"Unsubscribed from {a.username}."
                else:
                    msg = f"No subscription to '{command[1]}' found."

            except IndexError:
                msg = (
                    "Please enter an author to unsubcribe from."
                    " Alternatively, use !help for help."
                )
            except ValueError as e:
                msg = e
            except Exception as e:
                msg = e

            await message.channel.send(msg)

    @tasks.loop(minutes=int(os.getenv("REFRESH_INTERVAL")))
    async def update_articles(self):
        """
        Fetch new Articles for every subscribed to Author.
        """
        authors = session.query(Author).all()
        for author in authors:
            author.update_articles()

    @tasks.loop(minutes=int(os.getenv("POST_INTERVAL")))
    async def post_articles(self):
        """
        Post all articles with "posted" set to False, then set to True.
        """
        channel = super().get_channel(int(os.getenv("CHANNEL_ID")))

        if channel is None:  # Don't do anything if not connected to channel.
            return None
        
        articles = session.query(Article).filter(Article.posted == false()).all()

        for article in articles:

            author = article.get_author()

            article_data = {
                "author": author.username,
                "title": article.title,
                "author_url": author.page_url(),
                "article_url": article.url,
                "thumbnail_url": author.thumbnail,
                "published": article.published.split(" ")[:-2],
            }

            await channel.send(embed=new_article_message(**article_data))

            article.posted = True
            session.commit()


if __name__ == "__main__":
    # Connect to discord.
    substack_bot = SubstackBot()
    substack_bot.run(os.getenv("DISCORD_TOKEN"))
