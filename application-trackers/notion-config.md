parent_page_url: https://www.notion.so/33ae4796acaf80a7b50dca069e050aca
database_url: https://www.notion.so/f305a0c7116d4c07b1ca053e0b4adbdd
data_source_url: collection://1a670d77-7bce-4550-a318-89ca9b1032db

# Outreach Lane Signal Fields

Generated visualizer outreach rows may include lane-aware signal objects.

- `ContactSignal`: `alumniMatch`, `seniority`, `whyThisPerson`.
- `EngineerSignal`: all `ContactSignal` fields plus `teamMatch` (`exact`, `adjacent`, `unknown`, `mismatch`).
- `RecruiterSignal`: all `ContactSignal` fields plus `recruiterType` (`talent`, `technical`, `university`, `agency`, `in_house`, `unknown`) and `ownsRole` (`true`, `false`, or `null`).

Default inference is conservative: Georgia/UGA text sets `alumniMatch`; title keywords infer seniority; engineer `teamMatch` remains `unknown` until labeling; recruiter `ownsRole` remains `null` until explicit evidence.
