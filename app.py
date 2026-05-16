"""Learn to Invest — an educational app for new (and young) investors.

Focus: good habits, not hot stock tips. Lessons + calculators that show why
starting early and investing steadily beats trying to pick winners.
"""

import pandas as pd
import streamlit as st


# --------------------------------------------------------------------------
# Lessons
# --------------------------------------------------------------------------

LESSONS = [
    {
        "title": "1. What is a stock, really?",
        "body": """
A **stock** (or "share") is a tiny piece of ownership in a real company.
Buy one share of a company and you own a sliver of its offices, its brand,
its future profits.

Companies sell shares to raise money. People buy shares because they hope the
company grows and becomes worth more — and sometimes the company pays out a
slice of its profits, called a **dividend**.

The price of a share moves every second the market is open. It goes up when
more people want to buy than sell, and down when the opposite happens. Over a
single day that movement is mostly noise. Over **many years** it tends to
follow how well the company actually does.

**The key idea:** owning a stock means you own a business. You are not betting
on a number — you are part-owner of something real.
""",
        "takeaway": "A stock is part-ownership of a real company, not a lottery ticket.",
    },
    {
        "title": "2. Your secret weapon: compound growth",
        "body": """
This is the most important lesson, so read it twice.

When your money earns a return, that return *also* starts earning a return.
Then *that* earns a return. Money grows on top of money on top of money. This
snowball is called **compound growth**, and it is slow at first and then
shockingly fast.

Here is the part that matters for you: compounding rewards **time** more than
it rewards money. A 14-year-old with a small amount and 50 years ahead of them
can easily end up with more than a 40-year-old with a large amount.

You already have the rarest, most valuable thing in investing — **decades of
time**. You cannot buy it. Older investors wish they had it. You do.

Use the **Growth calculator** and **Start early** tabs to see this with real
numbers. It will surprise you.
""",
        "takeaway": "Time is the ingredient you have most of — and it matters more than money.",
    },
    {
        "title": "3. Index funds: the boring strategy that wins",
        "body": """
You asked which stocks will make the most money. Here is the honest answer:
**nobody knows.** Not me, not a fund manager, not anyone on YouTube. If a
person *could* reliably know, they would not be telling you for free.

So here is what professional investors actually recommend for almost everyone:
don't try to pick the winners. Buy a little piece of **all of them at once**.

An **index fund** is a single investment that holds hundreds or thousands of
companies. An "S&P 500" index fund, for example, holds 500 of the largest US
companies. When you buy one share of it, you instantly own a sliver of all 500.

Why this is powerful:
- You don't have to guess the winner — you own the whole market.
- If one company fails, it barely dents you. The others carry on.
- Fees are tiny, which means more of the growth stays yours.
- Study after study shows most professional stock-pickers **fail to beat a
  plain index fund** over the long run.

It is boring. Boring is the point. Boring is what works.
""",
        "takeaway": "Instead of picking the winner, own the whole market with an index fund.",
    },
    {
        "title": "4. Diversification: don't bet it all on one square",
        "body": """
**Diversification** means spreading your money across many different
investments instead of putting it all in one.

Imagine you put every dollar into one company and that company has a bad year.
You lose big. Now imagine you spread the same money across 500 companies in
different industries. One bad company barely matters — the rest keep going.

You are not trying to avoid *all* risk (that is impossible). You are trying to
avoid the kind of risk that can **wipe you out**. A single stock can go to
zero. A broad basket of hundreds of companies, historically, has not.

This is exactly why index funds (Lesson 3) are so useful — they hand you
diversification automatically in one purchase.

**Rule of thumb:** never put money you can't afford to lose into a single
stock — and never bet your whole future on one company, no matter how exciting
it sounds.
""",
        "takeaway": "Spread your money out so no single bad bet can sink you.",
    },
    {
        "title": "5. Dollar-cost averaging: invest a little, regularly",
        "body": """
New investors always ask: "Is *now* a good time to buy? Should I wait?"

Trying to guess the perfect moment is called **timing the market**, and even
the pros are bad at it. The fix is a habit called **dollar-cost averaging**:
you invest a **fixed amount on a fixed schedule** — say $25 every month — no
matter what the price is doing.

When prices are high, your $25 buys fewer shares. When prices are low, the same
$25 buys more shares. Over time you automatically buy more when it's cheap and
less when it's expensive, without having to predict anything.

Even better, it turns investing into a **routine** instead of a stressful
decision. You don't watch the news and panic. You just keep going.

The investors who do best are rarely the smartest — they are the most
**consistent**.
""",
        "takeaway": "Invest a set amount on a set schedule. Consistency beats clever timing.",
    },
    {
        "title": "6. Risk, reward, and your time horizon",
        "body": """
Every investment trades **risk** for **reward**. Higher potential reward almost
always comes with higher risk — a bigger chance of losing money along the way.

The stock market goes **down sometimes**. Not "if" — *when*. There will be
years where your account shrinks. This is normal and expected. It is the
"price of admission" for the long-term growth stocks have historically given.

Here is why it's far less scary for you than for an adult: your **time
horizon** — how long until you need the money — is huge. If you don't need this
money for 10, 20, 30+ years, a bad year is just a temporary dip on a long climb.

The danger is not the market dropping. The danger is **panic-selling** during
the drop, which turns a temporary dip into a permanent loss.

**Only invest money you will not need soon.** Money for next month's plans
belongs in savings, not stocks.
""",
        "takeaway": "Markets fall sometimes — that's normal. A long time horizon is what makes it safe.",
    },
    {
        "title": "7. Spotting hype, scams, and 'get rich quick'",
        "body": """
You want to make a lot of money. Good — that's a fine goal. But that exact
desire is what scammers and hype-sellers hunt for. Protect yourself.

**Warning signs that something is a trap:**
- It promises **guaranteed** or "risk-free" high returns. Nothing real does.
- It pressures you to act **right now** before you "miss out."
- A stranger online (or an influencer being paid) is pushing one specific
  stock or coin hard.
- It's hard to explain what the company or product actually *does*.
- It promises to **double your money** fast.

Real investing is slow and a little boring. It does not feel like a thrill
ride. If something feels exciting, urgent, and too good to be true — it is
almost always either a scam or gambling dressed up as investing.

**When in doubt, ask a trusted adult before putting in any money.** A good
investment will still be there tomorrow after you've thought it over.
""",
        "takeaway": "Guaranteed, urgent, or thrilling = danger. Real investing is calm and slow.",
    },
    {
        "title": "8. How a 14-year-old actually starts",
        "body": """
You can't legally open your own brokerage account until you're 18 — but you can
absolutely start now with a parent or guardian.

**The practical steps:**
1. **Talk to a parent or guardian.** They can open a **custodial account** (a
   brokerage account an adult holds *for* you until you're an adult). This is
   the normal, legal way for minors to invest.
2. **Start with money you won't need soon.** Birthday money, part of an
   allowance, earnings from a job — money you can leave alone for years.
3. **Begin with a broad index fund** (Lesson 3) so you're diversified from day
   one.
4. **Set up a regular habit** — even $10 or $25 a month (Lesson 5).
5. **Then mostly leave it alone.** Check it occasionally, not daily. Keep
   learning. Keep contributing.

That's it. It's not flashy. But started at 14 and kept up, this simple routine
is genuinely one of the most powerful money moves you can make.

**Your good-habits checklist:**
- [ ] I only invest money I won't need soon.
- [ ] I'm diversified (I own many companies, not one).
- [ ] I invest a set amount on a regular schedule.
- [ ] I won't panic-sell when the market drops.
- [ ] I ignore hype and "get rich quick" promises.
- [ ] I keep learning before I keep investing.
""",
        "takeaway": "Start now with a parent's custodial account, a broad index fund, and a steady habit.",
    },
]


# --------------------------------------------------------------------------
# Quiz
# --------------------------------------------------------------------------

QUIZ = [
    {
        "q": "Someone online guarantees you'll double your money in a month. What is this?",
        "options": [
            "A great opportunity — act fast!",
            "A warning sign of a scam or gambling",
            "Normal investing",
        ],
        "answer": 1,
        "why": "Nothing real guarantees high returns. Urgency + guarantees = danger.",
    },
    {
        "q": "What does an S&P 500 index fund let you do in a single purchase?",
        "options": [
            "Own a sliver of 500 large companies at once",
            "Own one hand-picked winning stock",
            "Avoid the stock market entirely",
        ],
        "answer": 0,
        "why": "An index fund gives you instant diversification across many companies.",
    },
    {
        "q": "The stock market drops 20%. You don't need this money for 20 years. Best move?",
        "options": [
            "Sell everything immediately to stop the loss",
            "Stay calm, keep your long-term plan, keep contributing",
            "Put all remaining money into one risky stock to recover fast",
        ],
        "answer": 1,
        "why": "Downturns are normal. Panic-selling turns a temporary dip into a permanent loss.",
    },
    {
        "q": "Which is YOUR biggest advantage as a 14-year-old investor?",
        "options": [
            "Having a lot of money to start with",
            "Knowing exactly which stock will win",
            "Decades of time for compound growth to work",
        ],
        "answer": 2,
        "why": "Time is the ingredient compounding needs most — and you have the most of it.",
    },
    {
        "q": "What is 'dollar-cost averaging'?",
        "options": [
            "Investing a fixed amount on a regular schedule",
            "Buying only when you're sure the price will rise",
            "Putting all your money in on one single day",
        ],
        "answer": 0,
        "why": "Investing a set amount regularly beats trying to time the perfect moment.",
    },
]


# --------------------------------------------------------------------------
# Calculator logic
# --------------------------------------------------------------------------

def project_growth(initial, monthly, years, annual_return_pct):
    """Month-by-month compound growth. Returns a yearly DataFrame and totals."""
    monthly_rate = annual_return_pct / 100 / 12
    balance = float(initial)
    contributed = float(initial)
    rows = [{"Year": 0, "Total you put in": contributed, "Account value": balance}]
    for month in range(1, years * 12 + 1):
        balance = balance * (1 + monthly_rate) + monthly
        contributed += monthly
        if month % 12 == 0:
            rows.append({
                "Year": month // 12,
                "Total you put in": contributed,
                "Account value": balance,
            })
    return pd.DataFrame(rows), balance, contributed


def final_value(initial, monthly, start_age, end_age, annual_return_pct):
    """Final account value for someone investing from start_age to end_age."""
    months = max(0, (end_age - start_age)) * 12
    monthly_rate = annual_return_pct / 100 / 12
    balance = float(initial)
    for _ in range(months):
        balance = balance * (1 + monthly_rate) + monthly
    return balance


def money(value):
    return f"${value:,.0f}"


# --------------------------------------------------------------------------
# UI tabs
# --------------------------------------------------------------------------

def render_learn():
    st.subheader("Lessons")
    st.caption("Eight short lessons on how investing actually works. Read them in order.")

    titles = [lesson["title"] for lesson in LESSONS]
    choice = st.selectbox("Pick a lesson", titles)
    lesson = LESSONS[titles.index(choice)]

    st.progress((titles.index(choice) + 1) / len(LESSONS),
                text=f"Lesson {titles.index(choice) + 1} of {len(LESSONS)}")

    st.markdown(f"### {lesson['title']}")
    st.markdown(lesson["body"])
    st.success(f"**Takeaway:** {lesson['takeaway']}")


def render_growth_calculator():
    st.subheader("Growth calculator")
    st.caption("See what a steady investing habit could grow into over many years.")

    col1, col2 = st.columns(2)
    with col1:
        initial = st.number_input("Starting amount ($)", min_value=0, max_value=1_000_000,
                                   value=100, step=50)
        monthly = st.number_input("Added every month ($)", min_value=0, max_value=100_000,
                                  value=25, step=5)
    with col2:
        years = st.slider("Years you keep investing", min_value=1, max_value=60, value=40)
        annual_return = st.slider("Assumed yearly return (%)", min_value=1.0, max_value=12.0,
                                  value=7.0, step=0.5)

    df, final_balance, contributed = project_growth(initial, monthly, years, annual_return)
    growth = final_balance - contributed

    m1, m2, m3 = st.columns(3)
    m1.metric("Money you put in", money(contributed))
    m2.metric("Growth on top", money(growth))
    m3.metric("Final account value", money(final_balance))

    st.markdown("#### Your money over time")
    st.line_chart(df.set_index("Year")[["Total you put in", "Account value"]])

    if contributed > 0:
        multiple = final_balance / contributed
        st.info(
            f"You would put in **{money(contributed)}** of your own money, and it could "
            f"grow into **{money(final_balance)}** — about **{multiple:.1f}x** what you "
            f"contributed. The gap is compound growth doing the work."
        )

    st.caption(
        "This is an estimate, not a promise. Real returns go up and down year to year and "
        "are never guaranteed. The long-run US stock market average has been roughly "
        "7-10% per year before inflation — but any single year can be very different."
    )


def render_start_early():
    st.subheader("Start early")
    st.caption("Why starting at your age beats starting later — even with the same monthly amount.")

    col1, col2 = st.columns(2)
    with col1:
        your_age = st.number_input("Your age now", min_value=10, max_value=30, value=14)
        monthly = st.number_input("Amount invested each month ($)", min_value=5, max_value=10_000,
                                  value=25, step=5, key="se_monthly")
    with col2:
        retire_age = st.number_input("Age you'd stop / cash out", min_value=40, max_value=80,
                                     value=65)
        annual_return = st.slider("Assumed yearly return (%)", min_value=1.0, max_value=12.0,
                                   value=7.0, step=0.5, key="se_return")

    later_age = 25
    you_value = final_value(0, monthly, your_age, retire_age, annual_return)
    later_value = final_value(0, monthly, later_age, retire_age, annual_return)

    you_contrib = monthly * 12 * max(0, retire_age - your_age)
    later_contrib = monthly * 12 * max(0, retire_age - later_age)

    c1, c2 = st.columns(2)
    c1.metric(f"You — start at {your_age}", money(you_value),
              help=f"You put in {money(you_contrib)} of your own money over the years.")
    c2.metric("Someone who waits until 25", money(later_value),
              help=f"They put in {money(later_contrib)} of their own money over the years.")

    chart_df = pd.DataFrame({
        "Investor": [f"Starts at {your_age} (you)", "Starts at 25"],
        "Final account value": [you_value, later_value],
    }).set_index("Investor")
    st.bar_chart(chart_df)

    if later_value > 0 and your_age < later_age:
        head_start = you_value - later_value
        extra_in = you_contrib - later_contrib
        st.success(
            f"By starting at **{your_age}** instead of **25**, you'd put in only "
            f"**{money(extra_in)}** more of your own money — but end up with about "
            f"**{money(head_start)}** more. That extra is pure compound growth, and it "
            f"exists only because you started earlier. **This head start cannot be bought "
            f"back later.**"
        )


def render_quiz():
    st.subheader("Quick quiz")
    st.caption("Check what stuck. Answer all five, then see your score.")

    answers = []
    for i, item in enumerate(QUIZ):
        pick = st.radio(f"**{i + 1}. {item['q']}**", item["options"],
                        index=None, key=f"quiz_{i}")
        answers.append(pick)

    if st.button("Check my answers", type="primary"):
        if any(a is None for a in answers):
            st.warning("Answer every question first.")
            return
        score = 0
        for i, (item, pick) in enumerate(zip(QUIZ, answers)):
            correct = item["options"][item["answer"]]
            if pick == correct:
                score += 1
                st.success(f"**{i + 1}. Correct.** {item['why']}")
            else:
                st.error(
                    f"**{i + 1}. Not quite.** The best answer is: *{correct}* — {item['why']}"
                )
        st.markdown(f"### Your score: {score} / {len(QUIZ)}")
        if score == len(QUIZ):
            st.balloons()
            st.success("Perfect. You've got the core habits down.")
        elif score >= 3:
            st.info("Good start. Re-read the lessons you missed and try again.")
        else:
            st.info("Worth another pass through the Lessons tab — then retake this.")


def main():
    st.set_page_config(page_title="Learn to Invest", layout="wide")
    st.title("Learn to Invest")
    st.caption("Good investing habits for new investors — built especially for getting started young.")

    with st.sidebar:
        st.header("Start here")
        st.markdown(
            "You said you want to **learn good investing habits** and **make money** — "
            "this app is built to do exactly that.\n\n"
            "**One honest thing first:** no app, expert, or website can tell you which "
            "stock will make the most money. Anyone who *promises* that is guessing or "
            "trying to take your money.\n\n"
            "What genuinely builds wealth is **habits + time** — and at your age, time is "
            "the one thing you have more of than almost any investor alive.\n\n"
            "Work through the **Lessons**, play with the **calculators**, then take the "
            "**Quiz**."
        )
        st.divider()
        st.caption(
            "Educational use only. This is not financial advice. Talk to a parent or "
            "guardian before investing real money."
        )

    learn_tab, growth_tab, early_tab, quiz_tab = st.tabs(
        ["Lessons", "Growth calculator", "Start early", "Quiz"]
    )
    with learn_tab:
        render_learn()
    with growth_tab:
        render_growth_calculator()
    with early_tab:
        render_start_early()
    with quiz_tab:
        render_quiz()


if __name__ == "__main__":
    main()
