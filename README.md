# Subscription SaaS FastAPI

A subscription-based web application built as a backend engineering test task. The app demonstrates a modular monolith architecture with FastAPI, PostgreSQL, SQLAlchemy 2.x async, Alembic, JWT authentication in HttpOnly cookies, Stripe Checkout, Stripe webhooks, mocked email notifications, mocked analytics, Docker Compose, and pytest coverage.

The UI is intentionally minimal Jinja HTML. The main focus is backend architecture, clear separation of concerns, maintainability, and pluggable external integrations.

## Quick Start For Reviewers

Follow this checklist to run the project with working Stripe subscription synchronization:

1. Copy environment variables:

```bash
cp .env.example .env
```

2. Fill `.env` with local and Stripe test values:

```text
JWT_SECRET_KEY=change-me-to-a-long-random-value
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_STARTER_WEEKLY=price_...
STRIPE_PRICE_STARTER_MONTHLY=price_...
STRIPE_PRICE_PRO_WEEKLY=price_...
STRIPE_PRICE_PRO_MONTHLY=price_...
```

3. Start the application and PostgreSQL:

```bash
docker compose up --build
```

4. In a second terminal, start Stripe webhook forwarding:

```bash
set -a
. ./.env
set +a
stripe listen --api-key "$STRIPE_SECRET_KEY" --forward-to localhost:8000/api/v1/webhooks/stripe
```

5. Copy the `whsec_...` value printed by Stripe CLI into `STRIPE_WEBHOOK_SECRET` in `.env`.

6. Restart the app so it loads the webhook secret:

```bash
docker compose restart app
```

7. Open the app:

```text
http://localhost:8000
```

8. Register a user, choose a plan, and pay with Stripe test card:

```text
4242 4242 4242 4242
Any future expiration date
Any 3-digit CVC
Any postal code
```

**Important:** Stripe webhooks are the source of truth. The success redirect only means the browser returned from Stripe Checkout. The local subscription status, dates, upgrades, downgrades, and cancellations are synchronized by webhook events. **Keep `stripe listen` running while testing payments.**

## Architecture

The project is organized as a modular monolith:

```text
app/
  api/                 request validation, response formatting, dependencies
  core/                settings, security, logging
  db/                  async database session and seed scripts
  models/              SQLAlchemy domain models
  schemas/             Pydantic request/response schemas
  repositories/        database access only
  services/            business workflows and orchestration
  integrations/        Stripe, email, analytics provider abstractions
  templates/           minimal Jinja pages
```

Routes do not call Stripe or contain subscription business logic. API handlers call services, services use repositories and provider interfaces, and infrastructure implementations sit under `app/integrations`.

## Key Decisions And Tradeoffs

Stripe webhooks are the source of truth. The success redirect page only confirms that the browser returned from Checkout; local subscription state is created and updated by webhook events.

Webhook processing is idempotent. Each Stripe event ID is stored in `webhook_events`; duplicates return `processed=false` and do not replay subscription mutations.

Payment is abstracted through `PaymentProvider`. Business services depend on `create_checkout_session`, `cancel_subscription`, `update_subscription_plan`, and `construct_webhook_event`, not the Stripe SDK directly. A PayPal, Paddle, or LemonSqueezy provider can be added without changing route logic.

Plans are stored in the database. Starter/Pro and Weekly/Monthly are seeded from environment-provided Stripe Price IDs, and plan ordering is represented by `tier_rank` and `billing_period_rank`. Adding yearly plans, promotional plans, or new tiers is primarily a data change.

Email and analytics are provider interfaces. Current implementations log events, but SendGrid, Mailgun, SES, Google Analytics, Mixpanel, or Amplitude can replace them without changing subscription workflows.

## Local Setup

Requirements:

- Docker and Docker Compose
- Stripe test account
- Optional: Stripe CLI for local webhook forwarding

Create a local environment file:

```bash
cp .env.example .env
```

Fill in `JWT_SECRET_KEY`, Stripe keys, webhook secret, and all four Stripe Price IDs.

## Stripe Sandbox Setup

1. Open the Stripe Dashboard in test mode.
2. Create two Products: `Starter` and `Pro`.
3. Add recurring Prices:
   - Starter weekly
   - Starter monthly
   - Pro weekly
   - Pro monthly
4. Copy each `price_...` ID into `.env`.
5. Copy your test secret key `sk_test_...` into `STRIPE_SECRET_KEY`.

Useful test card:

```text
4242 4242 4242 4242
Any future expiration date
Any 3-digit CVC
Any postal code
```

## Webhook Setup

The webhook endpoint is:

```text
POST http://localhost:8000/api/v1/webhooks/stripe
```

Handled events:

- `checkout.session.completed`
- `invoice.payment_succeeded`
- `customer.subscription.updated`
- `customer.subscription.deleted`

With Stripe CLI:

```bash
set -a
. ./.env
set +a
stripe listen --api-key "$STRIPE_SECRET_KEY" --forward-to localhost:8000/api/v1/webhooks/stripe
```

Run this command in a separate terminal while testing local payments. Stripe Checkout can accept a payment without this listener, but the local application will not update the subscription until the webhook is delivered.

Copy the displayed `whsec_...` value into `STRIPE_WEBHOOK_SECRET`, then restart the app container so the new environment value is loaded:

```bash
docker compose restart app
```

If Stripe CLI was not running during a test payment, the browser success page may appear but `Current Subscription` can still show the old state. Start the listener and repeat the test payment, or resend the event from the Stripe Dashboard/CLI.

## Run With Docker Compose

```bash
docker compose up --build
```

The app container runs:

```bash
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open:

```text
http://localhost:8000
```

## Alembic

Run migrations manually:

```bash
alembic upgrade head
```

Create a new migration after model changes:

```bash
alembic revision --autogenerate -m "describe change"
```

## Authentication Flow

Users register with email and password. Passwords are hashed with Argon2. Login issues a JWT access token in an HttpOnly cookie named `access_token`. Protected dependencies decode the token and load the current active user from the database.

Main endpoints:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

## Subscription Flow

1. User logs in.
2. User lists database-backed plans with `GET /api/v1/plans`.
3. User selects a plan.
4. Backend creates a Stripe Checkout Session.
5. Stripe redirects the user after payment.
6. Stripe webhook creates or updates the local subscription record.

Main endpoints:

- `GET /api/v1/plans`
- `POST /api/v1/subscriptions/checkout`
- `GET /api/v1/subscriptions/current`

## Upgrade And Downgrade Strategy

Plan changes in the HTML flow create a new Stripe Checkout Session for the selected plan. The user pays the selected plan as a full new subscription purchase. After `checkout.session.completed`, the webhook creates the new local subscription and cancels the previous Stripe subscription.

`PaymentProvider.update_subscription_plan()` remains part of the payment abstraction for providers or API use cases that support in-place plan updates, but the user-facing web flow intentionally uses Checkout so the payment step is explicit and never looks like a silent local plan rename.

The service classifies upgrade vs downgrade by comparing plan ranks from the database:

```text
score = tier_rank * 1000 + billing_period_rank
```

Higher score means upgrade; lower or equal score means downgrade. This keeps ranking extensible for yearly plans, promotional tiers, or additional commercial tiers.

Endpoint:

```text
POST /api/v1/subscriptions/change-plan
```

## Cancellation Flow

Cancellation immediately cancels the Stripe subscription and marks the local subscription as `canceled`. Stripe webhook events later reconcile final state.

Endpoint:

```text
POST /api/v1/subscriptions/cancel
```

Cancellation triggers:

- logged email notification
- mocked analytics event `subscription_canceled`
- structured subscription change log

## Environment Configuration

All configuration is loaded through `pydantic-settings`.

Important variables:

- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_STARTER_WEEKLY`
- `STRIPE_PRICE_STARTER_MONTHLY`
- `STRIPE_PRICE_PRO_WEEKLY`
- `STRIPE_PRICE_PRO_MONTHLY`
- `STRIPE_SUCCESS_URL`
- `STRIPE_CANCEL_URL`

Never commit real Stripe keys or JWT secrets.

## Testing

Install dependencies locally:

```bash
python3 -m pip install -e '.[test]'
```

Run tests:

```bash
python3 -m pytest -q
```

Coverage includes:

- registration
- login
- password hashing
- protected endpoints
- checkout session creation
- duplicate webhook processing
- subscription cancellation
- subscription plan changes

External payment, email, and analytics providers are mocked in tests.

## Logging And Error Handling

Structured JSON logs are emitted for registration, login, checkout creation, webhook processing, subscription changes, notifications, analytics events, and errors.

The API returns meaningful HTTP errors for duplicate registration, invalid credentials, missing auth token, invalid JWT, missing plans, missing subscriptions, invalid webhook signatures, and duplicate webhook events.

## Future Improvements

- Background worker for retries and async notification delivery
- Full audit log and subscription history
- Admin panel for plan management
- Organization accounts and seat-based billing
- Coupon and promotion support
- Free trials
- Webhook dead-letter queue
- Database-level advisory locking for high-concurrency webhook processing
- Real email and analytics providers
- OpenAPI client generation for frontend integration
