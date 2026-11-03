# Tests that could not be run (and why)
- **Real AI quality** (Sonnet/Haiku answers, Arabic caption quality, outline and critic quality): the audit used a mock AI on purpose (rule: no paid calls). Not proven.
- **Hesham's real face / Arabic captions with the Format Pack, icons and recap chain**: needs his footage on his Mac. Not proven.
- **Mac-only behaviour** (auto-start at login, port pick, browser open): audit ran on Linux.
- **Real AI outage / 429 on the live Nous account**: simulated with the mock only.
- **Lottie/motion files**: waiting for his files; checker has unit tests only.
- **Soak longer than 3 minutes**: a first 5-minute run was cut by a session restart; the 3-minute rerun is clean but short.
