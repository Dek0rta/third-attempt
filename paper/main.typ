// Third Attempt — paper source. Numbers in tables are read from results/*.json produced by analysis/.
// Build: uv run python paper/build.py

#let desc = json("/results/descriptive.json")
#let metrics = json("/results/model_metrics.json")
#let dec = json("/results/decisions.json")

#let thousands(n) = {
  let s = str(n)
  let out = ""
  let len = s.len()
  for (i, c) in s.clusters().enumerate() {
    if i > 0 and calc.rem(len - i, 3) == 0 { out += "," }
    out += c
  }
  out
}
#let pc(x, d: 0) = str(calc.round(100 * x, digits: d)) + "%"
#let num(x, d: 2) = {
  let s = str(calc.round(x, digits: d))
  if not s.contains(".") { s += "." }
  s + "0" * (d - s.split(".").at(1).len())
}

#set document(title: "The jump paradox", author: "Zakhar Sukhanov")
#set page(paper: "us-letter", margin: (x: 1in, y: 0.9in), numbering: "1")
#set text(font: "Libertinus Serif", size: 10.5pt)
#set par(justify: true, leading: 0.62em)
#set heading(numbering: "1.1")
#show heading.where(level: 1): it => block(above: 1.4em, below: 0.7em, text(size: 12pt, weight: "bold", it))
#show heading.where(level: 2): it => block(above: 1.1em, below: 0.6em, text(size: 10.5pt, weight: "bold", style: "italic", it))
#show figure.caption: it => text(size: 9pt, it)
#set figure(gap: 0.6em)
#show figure: set block(above: 1.2em, below: 1.2em)
#set table(stroke: none, inset: (x: 5pt, y: 3pt))
#show link: it => text(fill: rgb("#1e4fa0"), it)

#align(center)[
  #text(size: 17pt, weight: "bold")[The Jump Paradox: What 12 Million Powerlifting Attempts \ Can and Cannot Say About Attempt Selection]
  #v(0.6em)
  #text(size: 11pt)[Zakhar Sukhanov]
  #v(0.1em)
  #text(size: 9.5pt)[Independent researcher · #link("mailto:zexa1993@outlook.com")[zexa1993\@outlook.com] · #link("https://www.linkedin.com/in/zakhar-sukhanov-1ba2313b6/")[LinkedIn] · #link("https://github.com/Dek0rta")[GitHub]]
  #v(0.1em)
  #text(size: 9.5pt)[Code, data pipeline and calculator: #link("https://github.com/Dek0rta/third-attempt")[github.com/Dek0rta/third-attempt] · #link("https://dek0rta.github.io/third-attempt/")[dek0rta.github.io/third-attempt]]
  #v(0.1em)
  #text(size: 9.5pt)[Draft of 13 October 2026]
]

#v(0.8em)
#block(inset: (x: 2.2em))[
  #text(size: 9.5pt)[
    *Abstract.* In powerlifting each lift gets three attempts, and the lifter picks every weight. Using every competition attempt recorded in the public OpenPowerlifting database from 2000 to 2026 (#thousands(desc.n_attempts) attempts by #thousands(desc.n_lifters) lifters at #thousands(desc.n_meets) meets in #desc.n_federations federations), I study how those choices relate to outcomes. Success falls from 86–95% on first attempts to 46–64% on third attempts. Openers above a lifter's previous competition best are followed by a bomb-out (three misses) up to five times as often as openers at 85–92% of it. Success rates _rise_ with the size of the jump up to about 6–7%. This "jump paradox" cannot be causal, since a heavier bar is never easier for the same lifter on the same day; it shows that lifters choose jumps using information about how they feel. A consequence is that a naive model fitted to these data recommends implausibly large jumps. Using bounds that assume only that heavier weights are never easier (monotone treatment response), I show that a third-attempt jump of 3–4.5% maximizes the expected gain that can be guaranteed, in all three lifts and across subgroups. Success models validated on 2025–26 meets are well calibrated but weakly discriminating (AUC 0.60–0.65, and at most 0.67 with the lifter's own history). Misses earlier in a meet predict a shakier deadlift opener (odds ×0.76 per miss on a first or second attempt) after adjusting for its weight and the day's form. I release the code and a free calculator built on the models.
  ]
]

= Introduction

A powerlifting meet gives each lifter three attempts in the squat, the bench press and the deadlift. The best successful attempt in each lift counts toward the total, and a lifter who misses all three attempts in any lift "bombs out" and has no total. Attempt selection is therefore a sequence of decisions under risk: a bigger jump adds more kilograms if it succeeds but is more likely to fail. Coaches rely on rules of thumb, such as opening at about 90% of the planned best and making smaller jumps on later attempts @travis2021, but the sport now has a public record of millions of attempts that can test them.

Earlier work has described attempt success in samples of elite or single-federation lifters. #cite(<darragh2026>, form: "prose") model success against jump size in kilograms for IPF raw lifters and report that moderate jumps are associated with higher success than small ones. Opener weight has been related to the chance of winning @vandenhoek2022 @howells2022. #cite(<travis2021>, form: "prose") describe the attempt patterns of world-championship lifters who made all nine attempts. #cite(<nishihata2024>, form: "prose") show that competitive pressure lowers third-attempt bench success. In weightlifting, #cite(<genakos2012>, form: "prose") show that interim rank changes risk taking.

This paper makes four contributions. First, it uses all federations, equipment types and years that record attempts, and measures weights relative to each lifter's previous competition best. Second, it documents a _jump paradox_, explains why it is evidence of selection rather than a dose–response curve, and shows how it misleads naive models. Third, it answers the decision question that matters to lifters, which third-attempt jump to take, with partial-identification bounds @manski1997 that do not depend on how lifters choose. Fourth, it measures how predictable attempts are at all and tests whether misses carry over to later lifts, a question related to the "hot hand" debate @gilovich1985 @bareli2006 @miller2018.

= Data

== Source and processing

OpenPowerlifting is a volunteer-maintained, public-domain archive of meet results @opl. I use the snapshot of 10 October 2026, which contains 4,046,314 lifter-meet rows. A recorded attempt weight is positive if the lift was made and negative if it was missed. Not all federations publish individual attempts, so I keep only lift entries where all three attempts are recorded.

The same performance often appears several times because a lifter competed in several divisions at one meet; I keep one copy of each (lifter, meet, lift, attempts) combination. I drop 142 meets with ten or more entries and not a single recorded miss, since those federations evidently report only successful attempts. The analysis sample keeps meets from 2000 onward, men and women, known equipment, weights between 15 and 600 kg, and jumps between 0% and 30%.

== Variables

For each attempt I compute the jump over the previous attempt in percent and whether the previous attempt was made. The lifter's _previous best_ is their best successful competition lift in the same lift and equipment group (raw, wraps or equipped) at any strictly earlier meet in the database; #pc(desc.share_with_prior_best) of attempts have one. _Experience_ is the number of distinct earlier meet dates. Weights relative to the previous best are the key normalization: they make a 100 kg and a 300 kg lifter comparable without using anything that happened on the day.

The final sample has #thousands(desc.n_attempts) attempts in #thousands(desc.n_entries) lift entries by #thousands(desc.n_lifters) lifters at #thousands(desc.n_meets) meets held in #desc.n_meet_countries countries.

#let s = desc.success_by_lift_attempt
#figure(
  table(
    columns: (auto, auto, auto, auto),
    align: (left, right, right, right),
    table.hline(),
    table.header([*Lift*], [*1st attempt*], [*2nd attempt*], [*3rd attempt*]),
    table.hline(stroke: 0.5pt),
    [Squat], pc(s.Squat_1, d: 1), pc(s.Squat_2, d: 1), pc(s.Squat_3, d: 1),
    [Bench press], pc(s.Bench_1, d: 1), pc(s.Bench_2, d: 1), pc(s.Bench_3, d: 1),
    [Deadlift], pc(s.Deadlift_1, d: 1), pc(s.Deadlift_2, d: 1), pc(s.Deadlift_3, d: 1),
    table.hline(),
  ),
  caption: [Share of attempts made, 2000–2026.],
) <tab-success>

= What happens on the platform

Success falls with every attempt (@tab-success, @fig-success). Third attempts are made 64% of the time in the squat, 60% in the deadlift and only 46% in the bench press. At the same weight relative to the previous best, later attempts fail more often (@fig-pct). The fall is steepest in the deadlift, the last lift of the day.

#figure(image("/figures/fig1_success_by_attempt.png", width: 72%), caption: [Share of attempts made by lift and attempt number.]) <fig-success>

#figure(image("/figures/fig3_pct_of_best.png", width: 100%), caption: [Share made by attempt weight relative to the lifter's previous competition best. Bins with at least 500 attempts.]) <fig-pct>

*Openers and bomb-outs.* The median opener is 93–95% of the previous best. Bomb-out risk is flat at about 1% (squat and bench) and 0.3% (deadlift) for openers up to 92% of the previous best, then climbs steeply (@fig-bomb). Bench openers just above the previous best are followed by a bomb-out 5.8% of the time, against 1.0–1.1% at 85–92%. In the deadlift the ratio is similar (1.5–1.6% against 0.24–0.34%); in the squat it is smaller (2.6–3.2% against 1.0%).

This comparison is observational, but the direction of any bias is known. Lifters who open above their previous best are the ones who expect to have improved. If anything, that selection makes heavy openers look _safer_ than they would be for a typical lifter, so the true increase in risk is likely larger than the one shown.

#figure(image("/figures/fig4_bombout.png", width: 72%), caption: [Share of lift entries with three missed attempts, by opener weight relative to the previous best. Shaded: 95% Wilson intervals.]) <fig-bomb>

= The jump paradox

@fig-jump plots success against the jump over a made previous attempt. Between jumps of 0–2% and 6–7%, success on second attempts _rises_ from 69% to 81% in the bench press, from 73% to 85% in the squat and from 73% to 89% in the deadlift. Third-attempt squats and deadlifts show the same rise.

#figure(image("/figures/fig2_jump_paradox.png", width: 100%), caption: [Share made by jump size after a made previous attempt. Shaded: 95% Wilson intervals; bins with at least 1,000 attempts.]) <fig-jump>

This cannot be a causal effect. For one lifter on one day, adding weight to the bar can only make a lift harder. The rising part of the curve must come from _who_ chooses each jump. A lifter whose previous attempt moved slowly takes a small jump or none; a lifter whose previous attempt flew takes a large one. The jump encodes private information about the day, so a success-by-jump curve is a mixture of different lifters, not a dose–response curve. The same selection appears after a miss: going up after a missed attempt "succeeds" more often than repeating the weight (for example 45% against 34% on third-attempt deadlifts), most likely because lifters go up when the miss was technical rather than a lack of strength (@fig-miss).

Any analysis that reads these curves as advice inherits the bias. To show how large it is, I fitted the success model of @sec-models, plugged every jump from 0.5% to 15% into it for real 2025–26 lifters, and maximized expected gain. In all three lifts the "optimal" third-attempt jump was the largest one allowed, 15%, because predicted success falls more slowly than the jump grows. That answer is an artifact of selection.

#figure(image("/figures/fig5_after_miss.png", width: 80%), caption: [Share made after a missed attempt, by whether the lifter repeated the weight or went up.]) <fig-miss>

= Choosing the third attempt without assuming how lifters choose <sec-bounds>

== Bounds under monotone treatment response

Instead of a model of how lifters choose jumps, I use a single assumption: for a given lifter on a given day, if a weight would be made, any lighter weight would also be made. This is monotone treatment response (MTR) @manski1997. Consider third attempts after a made second attempt, group jumps into bins, and ask what share of _all_ these lifters would have made jump $t$.

For a lifter who chose a bigger jump than $t$ and made it, MTR says they would also have made $t$. For a lifter who chose a smaller jump and missed, MTR says they would also have missed $t$. Everyone else is unknown and could go either way. Writing $p_u$ for the share choosing bin $u$ and $m_u$ for their success rate,

$ sum_(u >= t) p_u m_u <= P(text("make") | t) <= 1 - sum_(u <= t) p_u (1 - m_u). $

Multiplying by $t$ gives bounds on the expected gain of jump $t$, in percent of the second attempt. These bounds do not depend on how lifters picked their jumps.

== Result: a 3–4.5% third attempt has the best guaranteed gain

The bounds are wide, as they must be without further assumptions (@fig-third). The upper bound keeps rising with the jump, so the data alone cannot rule out that some lifters would gain from large jumps. The lower bound, however, has a clear peak. Following Manski's treatment of decisions under ambiguity @manski2000, I report the _maximin_ jump: the one whose worst-case expected gain is highest. It falls in the 3.5–4.5% bin for the squat, the bench press and the deadlift, with a guaranteed gain of about 2.0%, 1.3% and 1.9% of the second attempt.

#figure(image("/figures/fig7_third_attempt.png", width: 100%), caption: [Expected gain of a third attempt by jump size. Shaded: range allowed by monotone treatment response. Line: worst case. Points: what lifters who chose each jump gained.]) <fig-third>

The result is robust (@tab-robust). On a finer 0.5% grid the maximin jump is 3.5–4% (squat), 3–3.5% (bench press) and 4–4.5% (deadlift). Within subgroups it stays between 2.5% and 4.5%; the only groups below 3.5% are male, equipped and very experienced benchers and very experienced squatters. A 3–4.5% third attempt is also close to what elite lifters do in practice @travis2021.

#let rob = dec.third_attempt_robustness
#figure(
  table(
    columns: (auto, auto, auto, auto),
    align: (left, center, center, center),
    table.hline(),
    table.header([*Group*], [*Squat*], [*Bench*], [*Deadlift*]),
    table.hline(stroke: 0.5pt),
    ..("All (0.5% grid)", "Men", "Women", "Raw", "Wraps", "Equipped", "0-1 prior meets", "8+ prior meets", "2020 and later", "IPF affiliates")
      .map(g => (g, ..rob.map(r => r.at(g).replace("-", "–") + "%")))
      .flatten(),
    table.hline(),
  ),
  caption: [Maximin third-attempt jump bin by subgroup (percent over a made second attempt).],
) <tab-robust>

Maximin is a cautious rule: it protects against the worst case allowed by the data, not the most likely one. A lifter who knows their second attempt was easy has exactly the information that the bounds refuse to assume, and may rationally jump more. The contribution here is a defensible default and a clear statement of what the data alone can support.

= How predictable is an attempt? <sec-models>

== Models

I fit one logistic regression per lift and attempt number, separately for lifters with and without a previous best. Features are linear splines in the weight relative to the previous best (knots at 85–110%) and in the jump (knots at 2–15%), the previous result, the first-attempt result and first-to-second jump (for third attempts), sex, equipment, drug testing, single-lift meets, experience bins, age bins and the 40 largest federations. Linear splines keep the model exactly reproducible in a browser; a test in the repository checks that the JavaScript and Python predictions agree to $10^(-9)$ on 720 real situations.

Models are trained on meets before 2025 and evaluated on 2025–26 meets they never saw. As a ceiling, I also add the lifter's own make rate over all earlier attempts, shrunk toward 75%.

== Calibrated, but weakly discriminating

#let pbm = metrics.filter(m => m.model.ends-with("_pb"))
#figure(
  table(
    columns: (auto, auto, auto, auto, auto, auto),
    align: (left, right, right, right, right, right),
    table.hline(),
    table.header([*Model*], [*Test attempts*], [*AUC basic*], [*+ federation*], [*+ own history*], [*Brier skill*]),
    table.hline(stroke: 0.5pt),
    ..pbm.map(m => (m.model.replace("_pb", "").replace("_", ", attempt "), thousands(m.n_test), num(m.auc_basic, d: 3), num(m.auc, d: 3), num(m.auc_history, d: 3), num(m.brier_skill, d: 3))).flatten(),
    table.hline(),
  ),
  caption: [Out-of-time performance on 2025–26 meets, lifters with a previous best. Brier skill is relative to the training-set success rate; it is reported for the federation model used by the calculator.],
) <tab-auc>

The predicted probabilities are well calibrated on the unseen meets (@fig-calib): when the model says 60%, close to 60% of attempts are made. But the models separate makes from misses only weakly. For lifters with a previous best, the AUC is 0.60–0.65 with the calculator's inputs and at most 0.67 with the lifter's own history (@tab-auc). Most of what decides an attempt is not in the public record: how the warm-ups went, technique on the day, fatigue, and judging.

#figure(image("/figures/fig6_calibration.png", width: 100%), caption: [Calibration on 2025–26 meets: deciles of predicted probability against the observed share made.]) <fig-calib>

= Do misses carry over?

The hot-hand literature asks whether outcomes cluster beyond chance @gilovich1985 @miller2018. In powerlifting the cleanest version of the question is across lifts: does missing squats and bench presses predict missing the deadlift opener, a weight usually planned before the meet and made 95% of the time?

I use full-power entries where the lifter has a previous best in all three lifts and made at least one squat and one bench press (#thousands(dec.carry_over_deadlift_opener.n_entries) entries). The outcome is the deadlift opener. Controls are its weight relative to the previous best (a linear spline), sex, equipment, testing and experience. A second model adds the day's form: the best squat and bench press of the day and the heaviest attempted weights, all relative to the previous bests. Standard errors are clustered by lifter.

#let co = dec.carry_over_deadlift_opener
#let orc(x) = num(x.odds_ratio, d: 2) + " (" + num(x.ci95.at(0), d: 2) + "–" + num(x.ci95.at(1), d: 2) + ")"
#figure(
  table(
    columns: (auto, auto, auto),
    align: (left, center, center),
    table.hline(),
    table.header([*Odds ratio per miss (95% CI)*], [*Weight controls*], [*+ day's form*]),
    table.hline(stroke: 0.5pt),
    [Miss on a 1st or 2nd squat/bench attempt], orc(co.weight_only.early_misses), orc(co.plus_day_form.early_misses),
    [Miss on a 3rd squat/bench attempt], orc(co.weight_only.third_misses), orc(co.plus_day_form.third_misses),
    table.hline(),
  ),
  caption: [Logistic regression of making the deadlift opener on earlier misses.],
) <tab-carry>

Each early miss lowers the odds of making the deadlift opener by about a quarter (odds ratio 0.76), and each third-attempt miss by about a fifth (0.82), with or without the day's form (@tab-carry, @fig-carry). Early misses matter more, which fits an information story: missing an easy attempt says more about the day than missing an ambitious one. These results show that misses predict later misses; they cannot separate a psychological effect from unmeasured fatigue, injury or a bad day.

#figure(image("/figures/fig8_carry_over.png", width: 68%), caption: [Share of deadlift openers made by the number of earlier misses, with 95% Wilson intervals.]) <fig-carry>

= A calculator that does not overclaim

The models power a free web calculator (#link("https://github.com/Dek0rta/third-attempt")[repository]). A lifter enters their previous best and their attempts so far; for every weight they could call next, it shows how often lifters in that situation made it, and for openers, the bomb-out risk when repeating after misses. That risk chains three model predictions; on 2025–26 meets its average (#dec.bomb_chain_check.map(r => pc(r.predicted, d: 2)).join(", ") for squat, bench press and deadlift) is close to, and slightly above, the observed rate (#dec.bomb_chain_check.map(r => pc(r.observed, d: 2)).join(", ")). Two design choices follow from this paper. The calculator states every number as a description ("_N_ of every 100 lifters in your spot made it") rather than a prediction for anyone who forces a weight. And it does not show an "expected gain" column, which would have reproduced the selection artifact of @sec-bounds; instead it marks how often lifters actually choose each jump, warns when a jump is rare, and highlights the 3–4.5% band of @sec-bounds.

= Limitations

The data are hand-entered from meet results and contain errors; the filters remove implausible values but not all mistakes. Federations that publish attempts may differ from those that do not. The previous best only covers meets in the database, so some lifters' true bests are higher. Weights are grouped into three equipment classes. The MTR assumption treats each lifter-day as having a fixed capacity; random technical faults weaken it slightly. With millions of observations almost every difference is statistically significant, so the paper emphasizes sizes and directions over p-values. Finally, none of the results identify psychological mechanisms.

= Conclusion

Public meet records can answer some attempt-selection questions and not others. They show clearly that later attempts fail more, that heavy openers raise bomb-out risk, and that misses travel through a meet. They cannot be read as dose–response curves for jump size, because lifters choose jumps with information the data do not contain; the jump paradox is the visible sign of that. With only the assumption that heavier is never easier, a third-attempt jump of 3–4.5% is the choice with the best guaranteed expected gain. All code, results and the calculator are open.

#v(0.6em)
*Acknowledgements.* Thanks to the OpenPowerlifting contributors who keep a sport's history public.

#v(0.4em)
#set text(size: 9pt)
#bibliography("refs.yml", title: "References", style: "apa")
