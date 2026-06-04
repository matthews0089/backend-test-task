from fastapi.templating import Jinja2Templates


def format_date(value):
    if not value:
        return "Pending Stripe webhook"
    return value.strftime("%B %d, %Y")


templates = Jinja2Templates(directory="app/templates")
templates.env.filters["date_only"] = format_date
