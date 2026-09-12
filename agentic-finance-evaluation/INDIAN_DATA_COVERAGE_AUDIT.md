# Indian Data Coverage Audit

> Generated from acquired artifacts and manifests. This report does not
> freeze context, discovery, re-evaluation, or OOD experiment dates.

## 1. Acquisition status

- Acquired and auditable datasets: **9**
- Acquired mandatory market/macro datasets: **8**
- Acquired support/calendar artifacts: **1**
- Pending/unavailable datasets: **5**
- Artifact read errors: **0**
- Pending datasets:
  - `crude_oil_brent_daily`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `mospi_cpi_combined_monthly`: pending_manual_download — [mospi_cpi_combined_monthly] Acquisition from MoSPI CPI / mospi.gov.in failed: MoSPI CPI data requires web download from mospi.gov.in. Automated download is not reliably possible. Release dates (critical for information availability) require separate collection from press release archives.

Manual download instructions:

MoSPI CPI Manual Download:
1. Visit: https://mospi.gov.in/consumer-price-indices-cpi
2. Download the "CPI Data" historical table (Excel or CSV)
3. Place at: data/raw/india/macro/cpi_combined.csv

For release dates (CRITICAL for information availability):
1. Visit: https://mospi.gov.in/press-release-consumer-price-index
2. Extract the date each month's CPI was released
3. Or use: https://www.rbi.org.in/scripts/Bs_PressReleaseDisplay.aspx
   (filter by CPI press releases)
4. Create a CSV with columns: reference_month, release_date
   reference_month format: YYYY-MM (e.g. 2024-01 for January 2024)
   release_date format: YYYY-MM-DD
5. Place at: data/raw/india/macro/cpi_release_dates.csv

Alternative automated source (secondary):
  RBI DBIE also carries CPI data:
  https://dbie.rbi.org.in/ → Price and Monetary → Consumer Price Index
  HOWEVER: DBIE may not include individual release dates.
  Use MoSPI as the primary source.

Expected CPI CSV structure:
  Month/Year | CPI_Combined (General) | CPI_Urban | CPI_Rural | ...
  OR: Month | Year | CPI | [sub-indices]
  Base year: 2012=100 for the new series

  - `mospi_iip_general_monthly`: pending_manual_download — [mospi_iip_general_monthly] Acquisition from MoSPI IIP / mospi.gov.in failed: MoSPI IIP data requires web download. Release dates (critical for information availability) require separate collection.

Manual download instructions:

MoSPI IIP Manual Download:
1. Visit: https://mospi.gov.in/index-industrial-production
2. Download historical IIP data (Excel or CSV)
3. Place at: data/raw/india/macro/iip_general.csv

For release dates (CRITICAL for information availability):
1. Visit MoSPI press releases or IIP release calendar
2. Record the date each month's IIP was first released
3. Create: data/raw/india/macro/iip_release_dates.csv
   Columns: reference_month (YYYY-MM), release_date (YYYY-MM-DD)

Alternative source:
  RBI DBIE: https://dbie.rbi.org.in/
  Navigate: Real Economy → Industry → IIP

Expected IIP CSV structure:
  Month/Year | General | Mining | Manufacturing | Electricity
  Base year: 2011-12=100 (current series)

  - `nse_equity_bhavcopy_daily`: pending_manual_download — No raw artifact supplied. Official-source acquisition requires manual download or source-specific access; this manifest intentionally records pending status and no coverage.
  - `rbi_gsec_364d_yield`: pending_manual_download — [rbi_gsec_364d_yield] Acquisition from RBI DBIE (364D yield) failed: DBIE automated fetch failed: HTTPSConnectionPool(host='dbie.rbi.org.in', port=443): Max retries exceeded with url: /DBIE/dbie.rbi?site=export&seriesId=BSR1:BISQ:A:A:4:0:WT.TBILL_364D&format=CSV (Caused by SSLError(SSLCertVerificationError(1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch, certificate is not valid for 'dbie.rbi.org.in'. (_ssl.c:1081)"))). RBI DBIE requires authenticated session or API key. Manual download required.

Manual download instructions:

RBI/DBIE 364D Yield Manual Download:
1. Visit: https://dbie.rbi.org.in/DBIE/dbie.rbi?site=statistics
2. Navigate: Financial Markets → Government Securities Market (or Money Market for T-Bills)
3. Find series for 364D yield/rate
4. Select maximum date range
5. Download as CSV
6. Place at: data/raw/india/fixed_income/tbill_364d.csv

Alternative (FBIL):
  https://www.fbil.org.in/#/home  → Benchmark Rates → FBIL T-Bill Rates
  (For T-Bills only; G-Sec rates remain from RBI/DBIE)

Expected CSV columns:
  Date | Yield (%) | [optional: Price, Security ID]


## 2. Dataset-by-dataset coverage

- Source: `MCX`
- Raw artifacts: `143 annual files`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (1).csv`: `d542195877bab59220f0c5e8661c911ad83e478445eb24cd5ad72c99540cad1a`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (10).csv`: `ba361c0baa4a60e8bcdfbb975bba82e9b69ed85736e02253e9a7ff60597f5bb7`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (100).csv`: `8a3db75017295219fb122fd3f41dae8b6aa2ca2322412a6eb3cd97bdb7930f6a`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (11).csv`: `bb56837550ca846fd087452f2f1956bd1a372a90ab120f55cce0cce314cc9a02`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (12).csv`: `441f6b2e3d0a1067674d6120856113c3267a6c7987ee4e90b2c4e4887cdad2f4`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (13).csv`: `94930a4bdf4487cc5d33a5a6c8f72c75274d9259ff86b2caf4335f3696e29e97`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (14).csv`: `9abd457f7f2900b265d04bd38087b38a13796417938a0c89ff426ef94d9dfdd1`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (15).csv`: `0509d61468e42ca7c74182a074f57bd0809807b0b3c28d4ba25f2b9cbaca50f6`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (16).csv`: `ccad4d834877d42ce19339c6c5256d09be102afd42a3770e4ab9783f5261ef5d`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (17).csv`: `4f98816d8cc94511920dff38179ddc42e9c762133fcc3b8166bca54e7c6b9976`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (18).csv`: `bc17a2f2485fb9c2f5253796328180a943e2841e38cec37cc58ca13f4b93d981`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (19).csv`: `4780828551f7738f3fb505afc7bb906e6015a54ac8a32e155bcf373608357c2a`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (2).csv`: `f86a68644468261d4d51f36eee7958f98d4c84cd4f42d679f20b690b2c690def`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (20).csv`: `f84a28b7b086cbe823e50cf19110dcecced9dbfc06d806240ee4890953c64389`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (21).csv`: `5faa5f7141ce49129d7ff10f983724a8cad579e26fba36513423f7bf3a12891c`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (22).csv`: `8de1d63a734d6041bce1d64cc0f75d6653848be5fc91dc5a2db22ae32f423376`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (23).csv`: `487bbe704dfd8259e5f9716d6087214edfbaf0d5f1555d8ce62c6626b9ab849c`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (24).csv`: `70c9c05fa04604dbe5db436d4525bde82c1c8341ef15601f86a9a05b7d3b7fdb`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (25).csv`: `34e07ec15a7dcee5ec50dfb4f83c042914f0fc6f396f74c09c14460b3f61ae06`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (26).csv`: `213bbefbdde9d7413a0d2531373945cab34e18433ba73641d329d7913d0de098`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (27).csv`: `3e80a5f4f6281de57fd9ef0da958a574c85eb9a656c407a88403ee8875723808`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (28).csv`: `925f7cc31bcffa39cc8e64daed84c878fd65596ccdef09c8a1c3e33bfc782c07`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (29).csv`: `dccd284de691036b636a97ae8ecea96b4deadc01d89b2971e2712395074c9018`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (3).csv`: `70e67d463da9e90f9db5c107acaeb51c80393b8458e0b9501993225fac13cd5d`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (30).csv`: `94e977d185e771daef5ddcc64560eef2da3401f0d0072e8ca4f6b4a7d5cfe0f5`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (31).csv`: `372fc41e4a130c7a54609ec564916d4d9b44c5da908af86adb542e0b2f324889`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (32).csv`: `4f85ff15180cc10f58dce57bd053c72df4985dd8f3eba855977f6b489575d3df`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (33).csv`: `4961a466424cb06a8b81c685cf59286d7f23541320105b1dd13035598ec2eff6`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (34).csv`: `6136e97ffe77e993832615180fb2e6ce0f07470c2252e84c8ff4c8713473ab5f`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (35).csv`: `f20e867d19419105e392634d8a5d20288d26bc8959be43c223f43e3d41a48699`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (36).csv`: `2be722df13a25dd47f827a0283806ce3d30e99225536cd418bc838c60fef9b07`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (37).csv`: `6d6e45807ee8d68e9f6becd3e463e3e826feda0097292d7b70ae10970f18f7e2`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (38).csv`: `33cb656fdaf3c0efa08e4e286eaa827e7c497103a583546f0ce8b7f9001c663a`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (39).csv`: `009e0fc09e5124d1dcbf1f41b808d49dc36ee63129f9743523b100a91949087f`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (4).csv`: `8292b647b6eaa0351c7df0aaaad754a8141057b1e44a59938e56865f02cee6be`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (40).csv`: `dbec39f5d8743cd41772ee27f4692a3b2860b72c2130720e54f9f24bedc3b914`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (41).csv`: `e8fb7784fc35bc2c0f953c87de8601ac9cff39633ad0ee426ba00b9fe11e57ab`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (42).csv`: `0eec714925e74a04b481b4270a501e5a97edb81dacae6c47bf13e5e253cd8279`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (43).csv`: `540c651459dc73f14739199789578ee3c23f9124cacc2de3736733288dbf42fe`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (44).csv`: `5e820273bad843365c062d4763617464ae360cabc0895b0ec40338dea07b476f`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (45).csv`: `937dee1790eced680b1f136fd3c0e4bdf22da0e7598c3591fcd91fb259f0dab8`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (46).csv`: `a9417d147318148eebcab81446c47624c1dd3b327ce950c13b4a103f9f43fac5`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (47).csv`: `c9389d65e025d061b9b68111e82fc872cf19a5b69667b12a01edd65f940bedcc`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (48).csv`: `eb0165da711b158cf87f2f79081330e59bea7e7b28e842c37c6182e28d673242`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (49).csv`: `f6a95bd8f503cb47d0228aff4a1f6b3bc36f6c82a86fb810f4ac5239edde565f`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (5).csv`: `164d31025447c0a46c56f79eedd0db616fa49f9710727da80bcf3e57e01f7342`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (50).csv`: `bf8ade430d59b22de81956d4ec8d6fa081271682d60f3203a06de2512c2ffc7b`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (51).csv`: `2d4e3251caf07c1477fe64611047fdbe604b679e1de45641d33de26370699a2b`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (52).csv`: `f2fed4a9682816710730694ab1eb1da3f48e8e89008391750519a0e4239cb2ba`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (53).csv`: `e58116ac6b0b3eeffcb4400d29f6381ee7c12ddef6b4455bc49b2e2b5bbe1f9c`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (54).csv`: `bee6195683d1b2cd6525d82b62649302918bae4c5fe54f39236597c4d6be390f`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (55).csv`: `728b9f3121b035cccda20708f16c7c4425e425d6b35ff216db0d5165e27ac9ac`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (56).csv`: `35d2da6c18bbb6df05ad4984c5b4b2a12f66deaeae629991feee5b6b4cc5b569`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (57).csv`: `4075f4f13dfdecc636f3909883e51ba8cab7cfe1c3c94c457c71d1a3cc5c2184`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (58).csv`: `ae4d0deb67ecbb29236c932ecb4e56bbc57f1f31a3d8f6750f9568535a466c26`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (59).csv`: `efd2215a72c9ba37faa7821eb67c4e805970e1a1f30e76cb32b34c972e3be806`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (6).csv`: `b6bef72dd25b25852c57a783bc26933f267f85b57f97eef23ae64659b5abb8b0`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (60).csv`: `fdc30dba3d771577dbea4e07ca464e054d43c229573bc5fbcf763b0bc72e4d06`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (61).csv`: `4703c18ae5399f438c58c416e8e5b543a203a684754690fb8018e39516a2c49c`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (62).csv`: `e753c18999fc77b99e74f4f3c52dd1ec1d4dae08992eab34d8a6200b9a91455e`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (63).csv`: `cc8f844d2a05d42b58c5bc57cb33cb72c97aa71c1d593e16b9ee0bea34fff159`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (64).csv`: `a210da6886decec25035c12841ec9d1968c2058ef28fadf15335521ad740f944`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (65).csv`: `1140a7fba75f2a22fca27bc81ee33c35168b242532e0da786ab21ccb053f3aa4`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (66).csv`: `3424c13c459fb345dc190e914701659066bf1879c9f1532eb50e84dc8b337c75`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (67).csv`: `ff2bc65674f74c9baf44313d2bece07cf7a1557adb171c6d3d9689cf7eccb2b9`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (68).csv`: `8af2f4f4deb7b755f2ec79bf82fe0f87efd019ff7d2c520f07b94657474fd67d`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (69).csv`: `e309681887281a9162b1b794cda0b3a057e10aff7ebc29ea6c79682d58a9b380`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (7).csv`: `94f40a937aa12ec389bc52b2e777707bbe98d8aac2c1b226f3482b0a3b8e14b5`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (70).csv`: `94b0da6e732f1ea5d907806aaab3967e1b07039b1f09d34bc4d32b94a103b9f9`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (71).csv`: `9ca8d4a026992574c40fcc4a09d9e3d65e7cf831cf612d13ccd8303ef0283ffb`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (72).csv`: `ca9459673d9e25ed91f689cc77f03a868e6c6801d1e02277513fe2e16d93be50`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (73).csv`: `d9624c338faa497881f569bd2150ea1c5688faac01466fd6f1ff1dcb6e061609`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (74).csv`: `fbc11609483a0ceff150d61387a8e96dd7a646d4d37dbbdfd73aac1acc6ed2f8`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (75).csv`: `03fbf0f8d65d6ad9106058d59190ce84a84bb0d3873bcc9bab0bf9cd186ce96e`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (76).csv`: `1fed2e0d98a3c80feb60b8cefb1bfd9fb0b94447cc92add5f257772ad2c368b8`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (77).csv`: `d8cb5bbd3e849c9e7aa0ccb3f66edcd94481fb0f43db2d5fa2680cba5acb6fe6`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (78).csv`: `f776551fc80f8f84f37aa81b1f8d42e83e4cd1b26ec35df23b8b84ccbc6d5332`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (79).csv`: `30aa04be310d4b85b933c53e6cf808b2fe95c2b6e8e9d87470723a8b6681c109`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (8).csv`: `c9b457d3e5a3d7941f7cb85273194c1ca7a2ddd189c0bf9b9e3d68da7b373670`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (80).csv`: `56e2fa8f1084231a370c4497b314e126a26c714e2b93e48e1ad5af3691149f4e`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (81).csv`: `bcab78f9e0cbe21e3df64524bc3798ddf19428a65715c15a8c10b29486f335ba`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (82).csv`: `2c9354e069415117997dbaca81b84c0a0659c294b33357868598a8f245b5f256`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (83).csv`: `71e37aa0fd60e3583e98c317c117d0ea84fec152a322b3cb1ceea83959946481`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (84).csv`: `5fec4816b953e6964cb8b50e28ba1a0ec16701c718e60e4897a610a7cc819ad1`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (85).csv`: `e6bb7c19178b8b9d3a9abc42e8d65c5cb97a0a997f8a8e19fdc4411b328fd461`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (86).csv`: `e00596241bec901055bb87be0b499f6ea580afc47f89ec58a7b9bc8709fd8eec`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (87).csv`: `98297142cbecdc7a54eebc1c891781b8185c598d0f12d592235b2c3574786eb3`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (88).csv`: `da2215c1aa333360d86cf7b554f1a2892b5556fdbe05d2849da8ec7adb2ab722`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (89).csv`: `754f43a1e3020efeef5c2429d4a0fa631f433a058a39be34f47259233f174510`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (9).csv`: `54dc4e9b09c50f0e45afca8a340de22d53a7cfe0d6681ac10e8eea9029149506`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (90).csv`: `e2b64ac9d917f339f28f1a80e4bb1dcbe5760ab67e0b516d5c2d10173a1ed902`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (91).csv`: `72caaff5d9adf7f942ed59a67e19ba67f5f91a8facdede775096faa2037e359c`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (92).csv`: `6505ff39ac66516a7f36c2dab123c5a233818a56dfc6d5722048b225d8e0bf8c`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (93).csv`: `ffe93124ebcd7335ee8c31d66be1c73fcdcbe3340cef71b534c39ab54b91ca30`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (94).csv`: `d46128436a2a489375f33082f6f855dff255639c25939c36b284057629594949`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (95).csv`: `8a2ff252d5264a1d84b6bacd666adeaa809753d1ed3292f98a73b91544fee6f2`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (96).csv`: `f0ad52318bcdfd9ffbf8baec3d88fea25871efac389d347c3b2b0da0737c8941`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (97).csv`: `b81b8a17f8f656466d88d6b1f8a9ad64602b1728ab38f4a9621daecd051a91f9`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (98).csv`: `a601c0a8691216e50b492c4cb6fed827d021f74abf387d89f4a61ff6400889c0`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 (99).csv`: `b304031014a19be53a27ebc8b2f7fa2ed9c7607c2dba741fc4e194c24a9b458f`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T170947.839.csv`: `540d41f00710cff7c764249edf3c084cac51c6a875122b0b9967c57ece9a3fb3`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171010.048.csv`: `b3dd99c8d9b41421b3609f85de5d3c5452c60a438e2768628d010e1b13a1a38b`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171015.932.csv`: `3c23baeeab97468ed3211ef3f01847bfe710a3058f99655f163e6c5dde9ac223`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171020.973.csv`: `f2a0510d524c0dcbfefa4eb773096f14319cf49226e6682bd0d53690d26edaca`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171027.024.csv`: `61c3d251503b19352214d6fca4e8a1ab8eac75f9fb060a81309098d3a43c67c0`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171032.931.csv`: `7e2bd09d4e02f66c588f10fc2c3e464c3e94328f1b9f3a04b38dde221965dc39`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171037.582.csv`: `e881e56ba0c43310abb56f9f6dd44221f91760279e6e07464ee58188aaf0803c`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171041.815.csv`: `b6dfc4bce2b6f1e0d1546947f6f76022a32aff2089325c2e710c707564a73f3f`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171046.115.csv`: `17396aaa3b3e43311b4145350f8f590447309b63679e3ef02c9c75b5ef838acc`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171050.489.csv`: `f714e1b3b86d22c3e4db04fccdcd5043c2b575ddf93fd5429d0891555785c2b7`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171054.857.csv`: `82488d73b1116defef0952e686a7e962ca89aab1fa5210c2f7649403792b5bbb`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171059.730.csv`: `89474fd7390a911626721c04139a883aac588ad9c34e6c574feb6fadaa166310`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171105.924.csv`: `617cb5e16093fc9a8c3ef33db821ad53971ff9329b6f8ec5014001842a11ae55`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171116.106.csv`: `dd596cddf14686ebdbcc971ea101d0dd3136eefd2a7c4d7e62a3a01949e9ae85`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171121.807.csv`: `53ee2c9ab46b835cef5b86d834ae122a12267361062913497752bb112324fe6f`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171126.731.csv`: `ab160cfd1e5bd8f9afa4c781055e5a32a2bcfa0e823653bfb79b08116a6d9315`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171131.272.csv`: `a3dd90e79af061a4aeccf490dc5b6f4d37b4b41213fe4f39289b69dcc854a3a9`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171135.988.csv`: `7b68bb95c903be88d41e985c22747f2c252ba5301b21b667734fb64ef04f55e4`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171140.955.csv`: `0202a900fcceeb5706caf92d358168aefbf1d778a51129411dd2aa972f7da1ea`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171147.514.csv`: `62afdc78c69e30c703d6c9d204a6d284bdcee6221144efb91960d77f889915e7`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171153.005.csv`: `834c1410dcabe35e196fe81a65ce20c58b2976f9e8797b30265be648f822bf7b`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171158.196.csv`: `67b50e85df7d50f977b53495e3ac2c862b963458dbed5b2acecc7e42c899adea`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171203.025.csv`: `569cafbaa3b5e5be6e2bc631b9a5fff75e1cb49d5e6c9574a70ddeca5aedde7e`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171208.501.csv`: `7606660997337611877b560385bb62a7e8753ebcd31e1147ac582f62ab6bf376`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171213.034.csv`: `41302adecda28fb31f0483de202046a6d7f66dcf4d052a1727527690ea0ea1e3`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171218.178.csv`: `2afe9d0f65cdd4b97047f1c820248dd1ee60128be2d0e85b7965a413ec18962a`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171224.751.csv`: `a153e5dd48f9b234786d69c032a7da53cd9226f5edeb91839d691f66d86444c5`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171229.626.csv`: `2ab86929aa294b0f4abcaaad2ef6d23a8b935143fe22eb245b7357822b9d88aa`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171234.311.csv`: `b9b699debb0ec6e09d9e314872a23a2946065e9d35532fc7ab46e2b45615fc4d`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171238.480.csv`: `158224ccdc41a5e4c4267873d60a79c6cc3deccfad4c4fe827e36bd8eb6429b8`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171243.130.csv`: `5ca26138716a9903d819395592f87c98a0f544a0feb6c8003fb196c42f4a599b`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171249.888.csv`: `544d11185f370f37bafbc1187e3e8de104faa9c930e3ef6548ca1acf37d023ab`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171255.138.csv`: `544d11185f370f37bafbc1187e3e8de104faa9c930e3ef6548ca1acf37d023ab`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171300.763.csv`: `3ad511a66eb74cd85707bc7dc02fb32154710a6586db29149a814bbecb88714b`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171305.554.csv`: `18ab1d8ac5bda6a7bf98a62b475a394f71dc403987be9c2091aeb65216f1d356`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171311.289.csv`: `afe603b284e5a3d6543c4fb6878c0341f31ce4f09d57e886dd431f8ae0bd1718`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171318.155.csv`: `a9a2f53e05c664fd775bfe5fe85e4e223343471d17e88cf47a6771b22954ac40`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171324.064.csv`: `18e6c4ca89d1b13c2da4ff41a81e064ea516fdf2107b24e2bfcfe912b7326a99`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171332.380.csv`: `d2c638aacb8332c6a2a1802f18143dbb6804c626053a35fb290de9c2ca72a7d3`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171337.154.csv`: `3bb752e1ad4299fdfcd103f04a25b7f5c5bd57d53b0a5d659b46c0f206edbd37`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003 - 2026-09-12T171341.987.csv`: `cc1d1e03e100b2bef812a9077a90178da951f6c0f9ea5b39f7eadac0b9c0dd8e`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012003.csv`: `ddef4adb6b60d2f68229764431fc6542545cd9ed6b2a32ab65c5244d7746a723`
  - `data/raw/india/gold/BhavCopyCommodiyWise_01012024.csv`: `cc1d1e03e100b2bef812a9077a90178da951f6c0f9ea5b39f7eadac0b9c0dd8e`
- Processed: `data/processed/india/instruments/mcx_gold_futures_individual_contracts.csv` SHA-256 `3106a2266c9ed01cf8eaafd158ca00eecbdcb7f416a6746b8d525460d9930d6d`
### `mcx_gold_futures_individual_contracts`
- Earliest: `2003-11-10`
- Latest: `2026-09-11`
- Observations: 29646
- Unique dates: 6353
- Duplicate timestamps: 23293
- Duplicate identifier pairs: 0
- Missingness:
  - `trade_date`: 0/29646 (0.00%)
  - `contract_symbol`: 0/29646 (0.00%)
  - `expiry_date`: 0/29646 (0.00%)
  - `close`: 0/29646 (0.00%)
  - `volume`: 0/29646 (0.00%)
  - `open_interest`: 0/29646 (0.00%)
  - `turnover`: 0/29646 (0.00%)
- Calendar: 495 non-trading observations; 0 heuristic trading days absent (UNAVAILABLE:nse_trading_holidays_2026.json)
- Note: WARNING: 23293 duplicate timestamps detected.
- Note: Repeated dates are evaluated with identifier columns; date repetition alone is not treated as a duplicate record.

- Source: `NSE`
- Raw artifacts: `17 annual files`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2009-to-03-11-2010.csv`: `7601fd2bdff590ab7f01fdb0458d3b141747325c8a094339151837e5ea4a32c1`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2010-to-03-11-2011.csv`: `2ad584779d4a6f95d847d2ce078d1db7169d33107ac0ba5a277bb9f47390992c`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2011-to-03-11-2012.csv`: `212310ce97cb7c383c349fdef8b115fd6616282ffc246ad69ae654811033bbcd`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2012-to-03-11-2013.csv`: `624d86e62904c9302d97cfcafffe47a0a82a73c71304b357991b798b684102fe`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2013-to-03-11-2014.csv`: `7862ff9403290e4743feb92af5fa2fce8f80c6b389b251716bcf4ae6abc58d0b`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2014-to-03-11-2015.csv`: `2306cd4fb06a995c4a83e26b7400c5929573870ce09ce2a04bb73d9310a515e5`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2015-to-03-11-2016.csv`: `d02650eafb9946377cbbe808d77c8660737610520c617c1be12d73401d60c890`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2016-to-03-11-2017.csv`: `a7e9a5696edb5f2a70dc63f5d180fe8f32df561dee9d622d283bc0cc02d526e6`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2017-to-03-11-2018.csv`: `19c79dc8f85cf0f49b2c2932e9d4b261d7ceb48e035239a8b9bb910bc387404a`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2018-to-03-11-2019.csv`: `b95e91fa698a49a27abfc227245a2b535e3e93b8a1021e404fdbd21f9901d0ee`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2019-to-03-11-2020.csv`: `ce1053f3f392b2609b2ba38e3675a329815dcf676df2a9678e2768a3d7defd04`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2020-to-03-11-2021.csv`: `c8237ada80a0000534b5695a67e9a90072bef539af4b5b59d952e1f3e0b41d78`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2021-to-03-11-2022.csv`: `5d8bb2305c9df88353553bc0c662f3a2e00542e830451249bf488cbfd344a511`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2022-to-03-11-2023.csv`: `1061957b64faf1694f2056e3ac590bd1a42a072b54e8aec57603a4f0140afea5`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2023-to-03-11-2024.csv`: `ff33dc2072af20f0b48c4bec893cff611d7fbe98d681b51a82204456023c1a3d`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2024-to-03-11-2025.csv`: `05e44ded91171b577f807564760ae40479f79549d79f00fff14f456afdccb52e`
  - `data/raw/india/india_vix/hist_india_vix_-03-11-2025-to-11-09-2026.csv`: `d5d78a3d3881a16868b4cd61659c7c9e6537a54b17df26dcd9141b9a13e7f039`
- Processed: `data/processed/india/market/nse_india_vix_daily.csv` SHA-256 `e7a35131fbe948ab7105ee14d86580877083524cd1c17933add387dd2977b5e3`
### `nse_india_vix_daily`
- Earliest: `2010-07-19`
- Latest: `2026-09-11`
- Observations: 4004
- Unique dates: 4004
- Duplicate timestamps: 0
- Duplicate identifier pairs: 0
- Missingness:
  - `date`: 0/4004 (0.00%)
  - `open`: 0/4004 (0.00%)
  - `high`: 0/4004 (0.00%)
  - `low`: 0/4004 (0.00%)
  - `close`: 0/4004 (0.00%)
  - `prev_close`: 0/4004 (0.00%)
  - `change`: 0/4004 (0.00%)
  - `pct_change`: 0/4004 (0.00%)
- Calendar: 17 non-trading observations; 0 heuristic trading days absent (UNAVAILABLE:nse_trading_holidays_2026.json)

- Source: `NSE`
- Raw artifacts: `30 annual files`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_01112004to01112005.csv`: `a5efd1ecac5d4a44c927093dbb8472c8991cf6153e1555d1d6aa11ebcab104a0`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_01112005to01112006.csv`: `af99869f988ee03a1fdc8084d1eff082a97a20f130b4ac465658f081a2a4bc07`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_01112006to01112007.csv`: `623ec36698fcf5fc057eac8348f3532d959a084dbbc1877fc99a26e687887cbf`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_01112007to31102008.csv`: `ce629419eebcf1a8edb8bff749b171afd63cd6c82af9c47b4e28b6d48d5bd99e`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_02112000to02112001.csv`: `84f17c90be61055a2563b724c28efc0add38a1de31e27aafaaf24157f6b419f0`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_02112001to02112002.csv`: `072f6953ca3d066ed35f8d1d74f33bcad159c8bf0d2eb34568189894dd17ff7d`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_02112002to02112003.csv`: `8c648ea77a8efc6aa4bd6a65fc4e2d08cc805e7a9e29b5de77c4dc774b63ab30`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_02112003to01112004.csv`: `0c007e00d0be8a35e66dde3530534689b691731efc61b2f657041b3d703b9caf`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_03111996to03111997.csv`: `dc5006508d1d95abd3579fc39bbb4bdbff18a3f859ef8e0d66259b616b49a258`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_03111997to03111998.csv`: `fe1a277751b9f5d389a17d6870eb354bf08f749985e813f3b29c3ad3401401c5`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_03111998to03111999.csv`: `7dd78070612ef1831f1738584de7b225e5b360e28ebb33e17410d92d770e5ae1`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_03111999to02112000.csv`: `c1297a653facf05cfaa3f0c7677d1eed2ba74f813698e6760f767370ba30ed91`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_28102024to28102025.csv`: `b0a7332f12f82530ab15fb3b6c71275f7caa2123b94ade1e1f1f9c9b0cda8791`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_28102025to11092026.csv`: `d9f7bbb9caeff3e84c5e4d5a5c6dd8cb4826add6704afa263f84bb99165c0da7`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_29102020to29102021.csv`: `8a789897d86d27d8034fae256c21da20748d0df56ad1966589a9a7a94a1307c7`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_29102021to29102022.csv`: `1b69544c8a3e41fa9e066f92b8a7f9b2804ad56b4fb7785387f9f96c231c1d8c`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_29102022to29102023.csv`: `dd04db22e49e84da2ac657c824cde5b7005f51191ca8980e4e1ed36fa2521f17`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_29102023to28102024.csv`: `7770ff52216fd1e833f8ad19d6528c7e4f82572947d7c6a1754df608ede0822f`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102012to30102013.csv`: `241eb11cd33e2ab9f3df2df2c196e5ce3fefd8bf6b3c353659939cac63f8a34b`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102013to30102014.csv`: `efb4f27b89bfc23afa0dd6e8389bef086a0e0d40cc5d7ab1ccf4a3fc8ad65668`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102014to30102015.csv`: `dd7d77b8723f1598300e9a536f5075b4121ae9f08fdb95410eb5976d6299c5c4`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102015to29102016.csv`: `71a53e6c07bfaea9bee4a4adbb9ad56aa7e4b7f103c691bbc88d818e934eac69`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102016to29102017.csv`: `1099a931fac3630f1009ddeed9453874759a5d8bf5772be54501170b236d1ec7`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102017to30102018.csv`: `6413e342f8d63c884aa9bfaa4caf15fc92f135593fb4dfb1a6c74d1e86e8f63f`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102018to30102019.csv`: `69ce58c6ccdcaf787520c0ee0ff542a2b3e6a49706748f7be40e3e55c9bd83c1`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_30102019to29102020.csv`: `ee3cbdf6efafc09c5781c3709a0d6d11a27b47641c2a2f5481a4a3ae21569314`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_31102008to31102009.csv`: `f4e7574c6952073752ebb2c77e4d2dd5288c67323e8438e580a1770b53c36757`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_31102009to31102010.csv`: `0bcb750cc6fa1a176b0a0da930a252b82ed9fdb63b18bde2fbd40ee212554767`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_31102010to31102011.csv`: `cc1f4487044cd623c56ce70bc950110714e83ad07923723aca79f5ff43ee9705`
  - `data/raw/india/indices/NIFTY 500_Historical_PR_31102011to30102012.csv`: `d103a71535a23f3f37b087dc50637dd8c347ac2d60ba59359d4e291641f0765a`
- Processed: `data/processed/india/market/nse_nifty_500_daily.csv` SHA-256 `217149c2aebdc8c531ff465df15c07138760d783497441eceb8f43da991d35a1`
### `nse_nifty_500_daily`
- Earliest: `1996-11-04`
- Latest: `2026-09-11`
- Observations: 7413
- Unique dates: 7413
- Duplicate timestamps: 0
- Duplicate identifier pairs: 0
- Missingness:
  - `date`: 0/7413 (0.00%)
  - `open`: 0/7413 (0.00%)
  - `high`: 0/7413 (0.00%)
  - `low`: 0/7413 (0.00%)
  - `close`: 0/7413 (0.00%)
- Calendar: 40 non-trading observations; 0 heuristic trading days absent (UNAVAILABLE:nse_trading_holidays_2026.json)

- Source: `NSE`
- Raw artifacts: `29 annual files`
  - `data/raw/india/indices/NIFTY 50-03-11-1997-to-03-11-1998.csv`: `366b0bab09ed341c21f4e5affc2e13cbb5c87bc915ef51af8272f99426f66d2f`
  - `data/raw/india/indices/NIFTY 50-03-11-1998-to-03-11-1999.csv`: `3632fed1f09095adce48d472322c7dbfb6a763a41f1ece8b2aec8db77c62b45a`
  - `data/raw/india/indices/NIFTY 50-03-11-1999-to-03-11-2000.csv`: `eb8d5af29b5a84fb764990d7aac4650db80c368301aea6d87c9eba8eb950cdca`
  - `data/raw/india/indices/NIFTY 50-03-11-2000-to-03-11-2001.csv`: `48bb8f7249deb5180dd3e3eeceaa3fc9d3191387d8a74a5ee69cfa51249c1f62`
  - `data/raw/india/indices/NIFTY 50-03-11-2001-to-03-11-2002.csv`: `f6f936cf62c3bd634ba274627d606fd791caa71e303dae19002ade02a97522a2`
  - `data/raw/india/indices/NIFTY 50-03-11-2002-to-03-11-2003.csv`: `4578bcc632aee42f54a0b4d0dc92442c5b8b0e11dde3291a5e7bdb22d14068b4`
  - `data/raw/india/indices/NIFTY 50-03-11-2003-to-03-11-2004.csv`: `d937a5d7d2bce8b91edfe261c511d7405ac89257eabe6e93112060f2b323443b`
  - `data/raw/india/indices/NIFTY 50-03-11-2004-to-03-11-2005.csv`: `eaba1f05f154513b2d06618e398a8e85bd1683966d2fcbd94d2fb8ae560b38ba`
  - `data/raw/india/indices/NIFTY 50-03-11-2005-to-03-11-2006.csv`: `0b49982170f7e5189fe860c1224dbe23bbd67832221de793ba5a143a715b41ef`
  - `data/raw/india/indices/NIFTY 50-03-11-2006-to-03-11-2007.csv`: `489e63ff6aea0976faf6a015c1a0addeccb775b0c5c786c126615254690c1ca2`
  - `data/raw/india/indices/NIFTY 50-03-11-2007-to-03-11-2008.csv`: `a56c480a788667e8b47008a596823113df183096b4e68105b58f47334d8fa04f`
  - `data/raw/india/indices/NIFTY 50-03-11-2008-to-03-11-2009.csv`: `2605e8eebf0bd123105a40f8a8b23b3202770928e4226e09a17c7c912941bcf3`
  - `data/raw/india/indices/NIFTY 50-03-11-2009-to-03-11-2010.csv`: `81424991f6d803adb95aa73cb669876b8a366e34d8d04274f09814600921d0ab`
  - `data/raw/india/indices/NIFTY 50-03-11-2010-to-03-11-2011.csv`: `0b4e62414e080843969f3aa1f1748ddfe20f5d0c13bd0427c3b4d346686296d4`
  - `data/raw/india/indices/NIFTY 50-03-11-2011-to-03-11-2012.csv`: `76dd025b4936f94b7d18a62c75fa82258c3f0f7e689e0a70a0a72bec1b23ad1d`
  - `data/raw/india/indices/NIFTY 50-03-11-2012-to-03-11-2013.csv`: `e2a2d361a76b85f87c642d3852c85791dd723a1ffea246a38d4ba63e7f254969`
  - `data/raw/india/indices/NIFTY 50-03-11-2013-to-03-11-2014.csv`: `b785239e9b250231d1df64529ea629370a755474491c969497c032d2d60fc495`
  - `data/raw/india/indices/NIFTY 50-03-11-2014-to-03-11-2015.csv`: `41bfc41638bef260830467cf3ba109d0d009849a9f9d33fdb9c7d81fe75f26c7`
  - `data/raw/india/indices/NIFTY 50-03-11-2015-to-03-11-2016.csv`: `e402cc0c0a7267fe795f5d89251904e5112382c7236b37663ff7781b42205f58`
  - `data/raw/india/indices/NIFTY 50-03-11-2016-to-03-11-2017.csv`: `eae2df9bdc73d44f490621ce34fe0b6366df3c91b354a47be51b2ab4648a5428`
  - `data/raw/india/indices/NIFTY 50-03-11-2017-to-03-11-2018.csv`: `494420fa872e1c3c9d38ecf9feb7eb7c3755b5b436ee8545d67f68dce8c18dd5`
  - `data/raw/india/indices/NIFTY 50-03-11-2018-to-03-11-2019.csv`: `81bf230522f292363200922551870cbc3843a40c76c0da84be10383860c21e8c`
  - `data/raw/india/indices/NIFTY 50-03-11-2019-to-03-11-2020.csv`: `064c507b2dd5768ff8e7c7254bb3e1f93b9b3e2a24bf615674753d5553788ae4`
  - `data/raw/india/indices/NIFTY 50-03-11-2020-to-03-11-2021.csv`: `076412647aeef2964cb218fe81be5ad27ec8af492b9cf6e5f90fd3dc8fc1353e`
  - `data/raw/india/indices/NIFTY 50-03-11-2021-to-03-11-2022.csv`: `f32200975b25f1e62f6da4f4db743d1bf1105e6e305d4a72cd27213540585c58`
  - `data/raw/india/indices/NIFTY 50-03-11-2022-to-03-11-2023.csv`: `12344a323fd3e5c7d48fb7b42e1e845324337c81b9ec281d5be7c93efc9297c6`
  - `data/raw/india/indices/NIFTY 50-03-11-2023-to-03-11-2024.csv`: `2e11609e8a0cf28b7563772cab5ad6cadfb5cfe4e91d37c816de22a69c240e63`
  - `data/raw/india/indices/NIFTY 50-03-11-2024-to-03-11-2025.csv`: `2978462d63df5d84b4f54bfa3aa0da6943c2c9fb44dd02afd54feeca3afa777e`
  - `data/raw/india/indices/NIFTY 50-03-11-2025-to-11-09-2026.csv`: `352711475a947e060a153cc4a689fb3f34be2f441a05c9773159de5ea62431ea`
- Processed: `data/processed/india/market/nse_nifty_50_daily.csv` SHA-256 `beff7b005ecf5a2134bc09ad0079af48c29a5071ea63c6657aaff9a2e349c09e`
### `nse_nifty_50_daily`
- Earliest: `1997-11-03`
- Latest: `2026-09-11`
- Observations: 7183
- Unique dates: 7183
- Duplicate timestamps: 0
- Duplicate identifier pairs: 0
- Missingness:
  - `date`: 0/7183 (0.00%)
  - `open`: 0/7183 (0.00%)
  - `high`: 0/7183 (0.00%)
  - `low`: 0/7183 (0.00%)
  - `close`: 0/7183 (0.00%)
  - `volume`: 0/7183 (0.00%)
  - `turnover`: 0/7183 (0.00%)
- Calendar: 37 non-trading observations; 0 heuristic trading days absent (UNAVAILABLE:nse_trading_holidays_2026.json)

- Source: `NSE`
- Raw SHA-256: `933cf5dc6dd4efe3b8db8ce6ecd6ecb2582929f5e0b4faffdb88e11cf4efdfbe`
- Processed: `data/processed/india/market/nse_trading_calendar_2026.csv` SHA-256 `3090d9f89784f264f7ee5b210c8f85a9f4851fb2bd71daa3754aedf536e08427`
### `nse_trading_holidays_2026`
- Earliest: `2026-01-01`
- Latest: `2026-12-25`
- Observations: 239
- Unique dates: 25
- Duplicate timestamps: not applicable (category membership)
- Duplicate identifier pairs: 0
- Note: Repeated dates are evaluated with identifier columns; date repetition alone is not treated as a duplicate record.
- Note: Repeated dates are legitimate market-segment membership; duplicate records are evaluated by `(market_segment, trading_date)`.

- Source: `RBI`
- Raw artifacts: `1 annual files`
  - `data/raw/india/fixed_income/50 Macroeconomic Indicators.xlsx`: `1072bfe9347c6c510c495d2d0894dc6e3931b23775a68faab5c74391f52e679d`
- Processed: `data/processed/india/market/rbi_gsec_10y_weekly.csv` SHA-256 `fb5c4845f143b11749df283d07d92b27ab050e207f714e329af38a54e18581a4`
### `rbi_gsec_10y_yield`
- Earliest: `2017-10-13`
- Latest: `2026-09-04`
- Observations: 465
- Unique dates: 465
- Duplicate timestamps: 0
- Duplicate identifier pairs: 0
- Missingness:
  - `observation_date`: 0/465 (0.00%)
  - `tenor`: 0/465 (0.00%)
  - `yield_pct`: 0/465 (0.00%)
- Calendar: 0 non-trading observations; 0 heuristic trading days absent (UNAVAILABLE:nse_trading_holidays_2026.json)

- Source: `RBI`
- Raw artifacts: `1 annual files`
  - `data/raw/india/fixed_income/50 Macroeconomic Indicators.xlsx`: `1072bfe9347c6c510c495d2d0894dc6e3931b23775a68faab5c74391f52e679d`
- Processed: `data/processed/india/market/rbi_tbill_91d_weekly.csv` SHA-256 `6ab7fff49cfb47a530839db2c485ea4b895eb62a00df169deea258e2d818d445`
### `rbi_gsec_91d_yield`
- Earliest: `2017-10-13`
- Latest: `2026-09-04`
- Observations: 458
- Unique dates: 458
- Duplicate timestamps: 0
- Duplicate identifier pairs: 0
- Missingness:
  - `observation_date`: 0/458 (0.00%)
  - `tenor`: 0/458 (0.00%)
  - `yield_pct`: 0/458 (0.00%)
- Temporal gaps above threshold: 5
- Calendar: 0 non-trading observations; 0 heuristic trading days absent (UNAVAILABLE:nse_trading_holidays_2026.json)
- Note: INFO: 5 gap(s) detected. First: (datetime.date(2023, 3, 24), datetime.date(2023, 4, 7))

- Source: `RBI`
- Raw artifacts: `62 annual files`
  - `data/raw/india/macro/rbi_handbook_2025-26_table40_policy_rates.xlsx`: `7ac18abb846add2e7aace7cb7ec262318616b60f1f0b1e1631511dd1522d160e`
  - `data/raw/india/macro/policy/rbi_annual_policy_2011-05-03_aps030511.pdf`: `46a27fe710049ec9d02235dd97f9ad182046475a610220b65d0f28868c9ad39e`
  - `data/raw/india/macro/policy/rbi_annual_report_2019-20_id1297.html`: `361a9cc47922ea11b6c8e87374c216ac3e39b302e0a6dc6173229d1c3f096734`
  - `data/raw/india/macro/policy/rbi_annual_report_2020-21_id1316.html`: `ffd011d14077ba79df77836bd8065efa6f53a20841d9a0d0ea4140a5b2daef8e`
  - `data/raw/india/macro/policy/rbi_annual_report_2022-23_id1374.html`: `196a17d1734f40748189ab021b83c90bb045c4790c506a505fd20d4bde1a5a2e`
  - `data/raw/india/macro/policy/rbi_annual_report_2024-25_id1473.html`: `530f268c05384af92d21885ffb9f9e707c52a1af62fd14681480fbc584edf183`
  - `data/raw/india/macro/policy/rbi_ar_2009-10_monetary_ch982.html`: `c8096d0740204690a35eb40c9d0f32450b69689fccf4deca892e05c7569e6f9e`
  - `data/raw/india/macro/policy/rbi_ar_2010-11_monetary_ch1000.html`: `d6fcaf5fd55ca6f1e7bba5fbc47ea3b6d9d1674fd8fd7aea9b1c49c1b552773b`
  - `data/raw/india/macro/policy/rbi_ar_2011-12_monetary_ch1040.html`: `a9cb8de5d35532153809b0589c32ac5eb07beb0835182443d853ce5f686b2262`
  - `data/raw/india/macro/policy/rbi_ar_2012-13_monetary_ch1081.html`: `6aa387dbd2e0867dbdf59e2b56cd300a2cca7997ceee94ed3c1a8ab58ba89a1e`
  - `data/raw/india/macro/policy/rbi_ar_2013-14_monetary_ch1121.html`: `37834d2f7e992cd33fa16b33a03e09ca3d186214c78b7875c4a3324c5ddb6a4e`
  - `data/raw/india/macro/policy/rbi_ar_2014-15_monetary_ch1149.html`: `de6dba0a4cd6692a901cded577dd4f4dcd082a483115357572e8d84c2466d713`
  - `data/raw/india/macro/policy/rbi_ar_2015-16_monetary_ch1176.html`: `c18e833bb1e044f9a66d96b7098e23a16f60d97ddf83961d9dcb7f1fa54c7abe`
  - `data/raw/india/macro/policy/rbi_ar_2016-17_monetary_ch1203.html`: `e9dfac9dff82d573bc75685b818f33c8116fa3affe39ab27950e5599e8a6b3b0`
  - `data/raw/india/macro/policy/rbi_ar_2017-18_monetary_ch1230.html`: `96321d30b2bf22cdd183187f38693f807169924fc2d245c74896bb37d0f8fffd`
  - `data/raw/india/macro/policy/rbi_ar_2018-19_monetary_ch1258.html`: `1245d13bb292af30cb6e56b17ca8551bbb7cbbbeaae53d814a45c2c1032e7e8d`
  - `data/raw/india/macro/policy/rbi_ar_chronology_2007-08_annex823.html`: `a265f24ed43423dbed1e6b3946143fd3421eed49b6adba2ae8d3601296e3a536`
  - `data/raw/india/macro/policy/rbi_ar_chronology_2008-09_annex907.html`: `0b220e4ba30830698c463d502c7dfc173bd5824604c84fb699145730475b712e`
  - `data/raw/india/macro/policy/rbi_ar_chronology_2014-15_annex1158.html`: `8bc81ba1c79d1e4244810bb585db94f21782603cf7edae3800728b7588fcfbb1`
  - `data/raw/india/macro/policy/rbi_ar_chronology_2015-16_annex1185.html`: `7f5fda745e3f166bbbf633e8a12dc3052a7aaada656820a05a6674841df78416`
  - `data/raw/india/macro/policy/rbi_ar_chronology_2016-17_annex1212.html`: `024196f226c4dbc45e9f5401f81e02e9965f980c3cbab56ee197169360ba8e3a`
  - `data/raw/india/macro/policy/rbi_ar_chronology_2017-18_annex1240.html`: `bd0ed31b44caa66db1616b514784a13dc65a97cf1f820a9a4646a8500e066448`
  - `data/raw/india/macro/policy/rbi_ar_chronology_2018-19_annex1268.html`: `270c69f30c965f0914ec4bc23a751045e25f38e34792767d11a879605e4bb686`
  - `data/raw/india/macro/policy/rbi_ar_chronology_2020-21_annex1326.html`: `bd75a445c661bad4c2cb66af9b4cbc4296998e6f0dd799efc37b2a632d791e7c`
  - `data/raw/india/macro/policy/rbi_ar_chronology_2022-23_annex1384.html`: `8d95fb9b015660393f8611b2b48a0f39abf35af7412d0999e1cf74cb1d4beee0`
  - `data/raw/india/macro/policy/rbi_ar_chronology_2023-24_annex1413.html`: `db91506b6b28b0d6d17df2d7ad955b6c9f586da9b6480dbc015244fd7c3b4cdf`
  - `data/raw/india/macro/policy/rbi_ar_chronology_2024-25_annex1443.html`: `654785ce6909da9044a748656f07419ee541cc76df78c9a0af9c7c10e427cbc5`
  - `data/raw/india/macro/policy/rbi_ar_chronology_covid2_annex1327.html`: `1d0bfe91c185e2c7bd1d8370e91b69408cae0e098e100bedadc611ee2bda79cf`
  - `data/raw/india/macro/policy/rbi_ar_chronology_covid3_annex1385.html`: `61468318a948e9a876125c7df21c4dbe10edc11356096329cbb2358622eb6c25`
  - `data/raw/india/macro/policy/rbi_ar_chronology_covid_annex1298.html`: `cf6038d2ded3a5b22905f8eaf5d31afdddb0277196f3ebc6559e0d7adf2bc791`
  - `data/raw/india/macro/policy/rbi_fqr_2011-07-26_id6631.html`: `965bc218b57ba440623866fd57a7957e7b71d4d3a029b12fb46e1e06e4c4329b`
  - `data/raw/india/macro/policy/rbi_gov_statement_2020-04-17_id3853.html`: `d676a5737bbfa5ccb7a675615acb5a82e179af89cc80d0d1f8587a9f9965e46b`
  - `data/raw/india/macro/policy/rbi_gov_statement_2020-05-22_id3859.html`: `af4756d43312deaf54b50821861a64134e170862b17944103685c392218f6d67`
  - `data/raw/india/macro/policy/rbi_gov_statement_2022-05-04_pr154mpc.pdf`: `99b8e4f1c679c83e23b9c5f1eaf372e1f726c6ba6ab026fbd81b250182af0fa0`
  - `data/raw/india/macro/policy/rbi_gov_statement_2022-06-08_pr333.pdf`: `9c515e882224eea72f2dbf51f9e006dd49c80e77a9327dad939e5022755d8568`
  - `data/raw/india/macro/policy/rbi_mcir_2011-01-25_id13156.html`: `7f18be1015c94d675b406dd315ec3334e6059e8b465a912f4dc70bfffe030f70`
  - `data/raw/india/macro/policy/rbi_mpc_minutes_2019-08-07_prid47941.html`: `0580e716ecd94d9aab7df7a3394eb224184111e268da8dbfdddd691ec2f984c8`
  - `data/raw/india/macro/policy/rbi_mpc_minutes_2022-06-08_prid53904.html`: `b20d98de6e6f90a3dcbdc030cf5fcad2a9c2296eed4eea999f0e4807e4e97556`
  - `data/raw/india/macro/policy/rbi_mpc_minutes_2022-08-05_prid54236.html`: `591dde41b93948e3f095d8513eb57811b9b45e6b9a65c96fc8c2b3cbe72f3720`
  - `data/raw/india/macro/policy/rbi_mpc_minutes_2022-12-07_pr1420.pdf`: `952bde1ad7d0bb0b7623ffa9f2bdedce07843ff96d2a8a5e01cb6055e02a097f`
  - `data/raw/india/macro/policy/rbi_mpc_resolution_2017-08-02_prid41391.html`: `9dacb99b8b54c334db3c6452e0cdb465e12240becb14fad0a293fdfbc0ec3274`
  - `data/raw/india/macro/policy/rbi_mpc_resolution_2018-06-06_pr3190.pdf`: `273d367176c46284d48da9c632ceacdf3b91869330188a372ddf144fbfb7273b`
  - `data/raw/india/macro/policy/rbi_mpc_resolution_2019-04-04_prid46722.html`: `6783180298ff760709dc8833c900d188ac836ac79748c36d8ee5deea467bc2b5`
  - `data/raw/india/macro/policy/rbi_mpc_resolution_2019-06-06_prid47225.html`: `849807cae7fcad015b41c71cd1d14a1570ff3747ce5abdd773f52e80ee972b1a`
  - `data/raw/india/macro/policy/rbi_mpc_resolution_2019-08-07_pr364df.pdf`: `8f3f4ee6cca2f24424d65f3affd94e405ff9c5c094a5ea6da980cb12baea33b7`
  - `data/raw/india/macro/policy/rbi_mpc_resolution_2020-03-27_prid49581.html`: `7330bb03caa3a57e3909703559fb08f89f30f0de74c094d721750928cf56e187`
  - `data/raw/india/macro/policy/rbi_mpc_resolution_2025-02-07_prid59692.html`: `00e22a6c1e80e74f3dd8f4196c95b51261961a69c7fcef38d5636c3e27b0ae1b`
  - `data/raw/india/macro/policy/rbi_mpc_resolution_2025-04-09_prid60176.html`: `8e4c30d6a71a35815c1a9c80b2ead7ef7126d0b16c5eaa6aae251f3fb112c89f`
  - `data/raw/india/macro/policy/rbi_mpc_resolution_2025-06-06_prid60604.html`: `0d058895c27f95209e61d5d4dbc647b916d45bea5ce9f0b85cbe41422bba177e`
  - `data/raw/india/macro/policy/rbi_mpc_resolution_2025-12-05_prid61749.html`: `5d7e974a794a2aae4eac2d766de16beee5854aab5fe2c7a7c1d3fe5bf78fdf87`
  - `data/raw/india/macro/policy/rbi_mpc_statement_2016-12-07_id2075.html`: `4e77dc744022a42d495dce940faa79c75cf48b99a07a32287fde79e002f6b0d1`
  - `data/raw/india/macro/policy/rbi_mpc_statement_2017-04-06_pr26893.pdf`: `fdcecd2f0510b2278f16b6f6cd52eb4a8d7e406b10efa084d8fa0632b128d2d8`
  - `data/raw/india/macro/policy/rbi_mpc_statement_2019-10-04_pub19338.html`: `76b708b68b300a113cead7fc17a1529bd84db3e1b92f555ddb51550684aefb22`
  - `data/raw/india/macro/policy/rbi_mpc_statement_2019-12-05_pub19409.html`: `1e4b2360bdaad38d0f47852333c2a0ea8b9d52ad08bfbc1c647d6a5cefea8f7c`
  - `data/raw/india/macro/policy/rbi_mpc_statement_2022-04-08_id3353.html`: `86a2ab3ec0b0db3085d696b82cfd64ad885a45bf68f8dd526cb459a8329b0145`
  - `data/raw/india/macro/policy/rbi_mpc_statement_2022-05-04_id3356.html`: `3467f15bb6c1148ca644deba10cd9fcbc1edca799fbba15d44918a7dcf0e69ed`
  - `data/raw/india/macro/policy/rbi_mpc_statement_2022-06-08_id3362.html`: `e9a12945ded497896c09135be7d924849f8214dca5be28cd748a3a1113ce5350`
  - `data/raw/india/macro/policy/rbi_mpr_2016-10-04_pub17385.html`: `2ed214d45cb0ea3c381264e39b628031ea744ec1f6c2ab0bf478c1b99ef580e7`
  - `data/raw/india/macro/policy/rbi_msf_circular_2016-10-04_id2280.html`: `d24914f2209ed93978a5922d029816be301ca8cb74c2ec587c2ee162ac4f1224`
  - `data/raw/india/macro/policy/rbi_publications_2012-13_statements_id15544.html`: `6b12ef33651bd43af5ac1fb0cfde34835862cf11a2cabd42bd824bc4acc63e06`
  - `data/raw/india/macro/policy/rbi_sdf_statement_2022-04-08_prid53536.html`: `1fd42e09d633e4000af605ca389ce346f1a5fbb360e8e1463bbd74ef4f1d686c`
  - `data/raw/india/macro/policy/rbi_statement_2015-09-29_prid35087.html`: `e901cfa6d2f2d0ef6b66954df2d78c50435294e5cc2acc39436f2d8969cd7a7f`
- Processed: `data/processed/india/macro/rbi_policy_rate_events.csv` SHA-256 `24b4e91742743da3bae47b8cc2f1c6b75d30211937f2b90cb1c2c280eb957db7`
### `rbi_policy_rate_events`
- Earliest: `2008-06-12`
- Latest: `2025-12-05`
- Observations: 187
- Unique dates: 61
- Duplicate timestamps: 126
- Duplicate identifier pairs: 0
- Missingness:
  - `announcement_date`: 27/187 (14.44%)
  - `effective_date`: 0/187 (0.00%)
  - `stance`: 112/187 (59.89%)
- Temporal gaps above threshold: 2
- Availability violations: 0/187
- Note: WARNING: 126 duplicate timestamps detected.
- Note: Repeated dates are evaluated with identifier columns; date repetition alone is not treated as a duplicate record.
- Note: INFO: 2 gap(s) detected. First: (datetime.date(2020, 5, 22), datetime.date(2022, 4, 8))

- Source: `RBI`
- Raw artifacts: `1 annual files`
  - `data/raw/india/currency/BankWise.xls`: `4b2b6cd815a53357ebdb3d72cc4728a80922fa5f57bafc26495d6dc3600a5068`
- Processed: `data/processed/india/market/rbi_usd_inr_daily.csv` SHA-256 `878d4e0ecd080e8d4700a7d1e947301db904f9b38f4b8f21149d51da668aff6b`
### `rbi_usd_inr_daily`
- Earliest: `1998-08-25`
- Latest: `2026-09-11`
- Observations: 5878
- Unique dates: 5878
- Duplicate timestamps: 0
- Duplicate identifier pairs: 0
- Missingness:
  - `date`: 0/5878 (0.00%)
  - `rate`: 0/5878 (0.00%)
- Temporal gaps above threshold: 2
- Calendar: 2 non-trading observations; 0 heuristic trading days absent (UNAVAILABLE:nse_trading_holidays_2026.json)
- Note: INFO: 2 gap(s) detected. First: (datetime.date(2018, 7, 9), datetime.date(2018, 7, 24))

## 3. Missingness

Missingness is reported per required field above. No values were forward-filled by this audit.

## 4. Duplicate analysis

Duplicate timestamps and date/identifier pairs are reported per dataset above.

## 5. Calendar analysis

Trading-day checks use the versioned NSE holiday artifact when its coverage includes the audited years. Years outside that artifact are reported as calendar-unavailable rather than inferred from weekdays.

## 6. Information-availability analysis

Macro and policy datasets must carry observation_date and availability_date. Values are not eligible for agent observations before availability_date.

## 7. Common intersection

- Status: **INCOMPLETE_DATASET_SET**
- Earliest common usable date: `not computable`
- Latest common usable date: `not computable`
- Calendar duration: 0 days
- Datasets included: none
- Datasets excluded: mcx_gold_futures_individual_contracts, mospi_cpi_combined_monthly, mospi_iip_general_monthly, nse_india_vix_daily, nse_nifty_500_daily, nse_nifty_50_daily, rbi_gsec_10y_yield, rbi_gsec_364d_yield, rbi_gsec_91d_yield, rbi_policy_rate_events, rbi_usd_inr_daily
- Jointly usable sessions: 0
- Limiting datasets: none
- Exclusion reasons:
  - `mcx_gold_futures_individual_contracts`: Dataset is not experiment-eligible.
  - `mospi_cpi_combined_monthly`: Dataset not audited — no coverage data available.
  - `mospi_iip_general_monthly`: Dataset not audited — no coverage data available.
  - `nse_india_vix_daily`: Dataset is not experiment-eligible.
  - `nse_nifty_500_daily`: Dataset is not experiment-eligible.
  - `nse_nifty_50_daily`: Dataset is not experiment-eligible.
  - `rbi_gsec_10y_yield`: Dataset is not experiment-eligible.
  - `rbi_gsec_364d_yield`: Dataset not audited — no coverage data available.
  - `rbi_gsec_91d_yield`: Dataset is not experiment-eligible.
  - `rbi_policy_rate_events`: Dataset is not experiment-eligible.
  - `rbi_usd_inr_daily`: Dataset is not experiment-eligible.

## 8. Data-quality blockers

- No artifact read errors were encountered.

## 9. Leakage findings

- Leakage validation status: **EVALUATED**
- Datasets checked: corporate_actions, gold, policy, preprocessing, price
- Confirmed leaks: 0
- Potential leaks: 1
- Mitigated issues: 1
- Unresolved issues: 0
- Gold futures must remain contract-level until a roll method is selected and independently audited.

## 10. Recommended next methodological decision

Complete official-source acquisition and release-date verification for the mandatory datasets. Then review this audit to define the longest clean common period before selecting any temporal split boundaries.
