import discord


class Colors:
    """
    Default color scheme.
    """

    green = 0x00FF04
    purple = 0xF613CD


def help_message():
    """
    Bot help message.
    """
    embed = discord.Embed(
        title=">_", description="List of commands:", color=Colors.green
    )
    embed.add_field(
        name="Subscribe:", value="!subscribe <author>: Add subscription to author."
    )
    embed.add_field(
        name="Unsubscribe:",
        value="!unsubscribe <author>: Remove subscription to author.",
    )
    embed.set_footer(text="Remember to use the subdomain e.g. subdomain.substack.com.")
    return embed


def new_article_message(
    author=None,
    title=None,
    author_url=None,
    article_url=None,
    thumbnail_url=None,
    published=None,
):
    """
    Formatted new article message.
    """
    embed = discord.Embed(
        title=f"{author}", description=f"[{title}]({author_url})", color=Colors.purple
    )
    embed.set_thumbnail(url=f"{thumbnail_url}")
    embed.set_footer(text=f"{published}")
    return embed
