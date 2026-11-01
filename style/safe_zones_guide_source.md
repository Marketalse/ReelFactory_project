# Instagram & TikTok Safe Zone & Design Guide

When creating vertical videos and visual content for social media platforms like Instagram and TikTok, UI overlays (buttons, captions, headers, handles) can obscure critical visual content or text. 

This guide provides precise dimensions, pixel measurements, and design instructions to ensure your content is fully visible and engaging across platforms.

---

## 1. Canvas Basics & Aspect Ratios

* **Standard Canvas Resolution:** $1080 \times 1920$ pixels (9:16 aspect ratio).
* **Frame Rate:** 30fps or 60fps.
* **Feed Preview Grid (Instagram):** 1:1 ratio ($1080 \times 1080$ pixels) centered in the 9:16 frame.

---

## 2. Instagram Safe Zone Specifications

### A. Instagram Reels (9:16 Vertical Video)
* **Canvas Size:** $1080 \times 1920$ px
* **Top Safe Zone (Header Overlay):** 
  * **Reserved Space:** Top **220 px to 250 px**
  * **UI Elements:** Back arrow, camera icon, audio track title, audio visualizer.
  * **Instruction:** Avoid placing main titles, logos, or face focal points in this top zone.
* **Bottom Safe Zone (Caption & Controls Overlay):** 
  * **Reserved Space:** Bottom **350 px to 420 px**
  * **UI Elements:** Account name, follow button, caption text (up to 4 lines expanded), sound bar, interactive stickers, and original audio link.
  * **Instruction:** Place no critical graphics, subtitles, or lower-third text in this area.
* **Right Side Safe Zone:** 
  * **Reserved Space:** Rightmost **120 px**
  * **UI Elements:** Like (heart), Comment, Share (paper airplane), and More options (three dots).
* **Left Side Safe Zone:** 
  * **Reserved Space:** Leftmost **108 px** (10% padding for screen edge curvature).
* **Core Safe Zone ("Golden Box"):** 
  * Dimensions: **$852 \times 1250$ px** (centered horizontally, placed between $Y = 250\text{px}$ and $Y = 1500\text{px}$).

### B. Instagram Stories (9:16 Vertical Visuals)
* **Top Safe Zone:** Top **200 px** reserved for handle name, progress bars, and exit button.
* **Bottom Safe Zone:** Bottom **250 px** reserved for "Send Message" field, share button, and swipe-up / sticker link buttons.

### C. Instagram Feed Carousels (4:5 Aspect Ratio)
* **Canvas Size:** $1080 \times 1350$ px.
* **Safe Zone:** Entire canvas is visible, but maintain a **108 px** padding on all sides for optimal aesthetic presentation.

---

## 3. TikTok Safe Zone Specifications

TikTok has a denser UI overlay, particularly on the right side and lower section of the screen.

### TikTok Video (9:16 Vertical Video)
* **Canvas Size:** $1080 \times 1920$ px
* **Top Safe Zone (Navigation Bar):** 
  * **Reserved Space:** Top **160 px to 200 px**
  * **UI Elements:** "Following" / "For You" tabs, search bar, live stream badge, and audio icon.
* **Bottom Safe Zone (Caption & Interactive Bar):** 
  * **Reserved Space:** Bottom **320 px to 380 px**
  * **UI Elements:** Creator handle (@username), video description/captions, hashtags, sound track marquee/ticker, add comment bar.
* **Right Side Safe Zone (Action Column):** 
  * **Reserved Space:** Rightmost **160 px**
  * **UI Elements:** Avatar profile picture, Like count, Comment count, Bookmark/Save count, Share button, spinning record disk icon.
* **Left Side Safe Zone:** 
  * **Reserved Space:** Leftmost **60 px** to avoid bezel cutoffs on dynamic display smartphones.
* **Core Safe Zone ("Golden Box"):** 
  * Dimensions: **$860 \times 1340$ px** (aligned to the left side, starting $X = 60\text{px}$ and spanning $Y = 200\text{px}$ to $Y = 1540\text{px}$).

---

## 4. Animation & Subtitle Safe Zone Instructions

When adding motion graphics, dynamic text, kinetic typography, or closed captions, adhere to the following rules:

1. **Subtitle Position:**
   * Align captions centrally between $Y = 1200\text{px}$ and $Y = 1450\text{px}$ relative to a standard $1080 \times 1920$ canvas.
   * Do **not** place subtitles at the absolute bottom ($Y > 1550\text{px}$) as TikTok and Reel captions will render over them.
2. **Animation Paths:**
   * Keep key visual animations (slides, pops, zooms) within the central **$800 \times 1200$ px** zone.
   * If animating text from off-screen, ensure its final rest position lies completely inside the Golden Safe Zone.
3. **Text Line Width:**
   * Limit automated or manual text width to a maximum of **780 px** horizontally centered. This guarantees text won't touch or slide under the right-hand action column buttons (Likes, Comments, Shares).

---

## 5. Creator & Designer Workflow Checklist

- [ ] **Canvas Verification:** Set project timeline to $1080 \times 1920$ px at 30 or 60 fps.
- [ ] **UI Overlay Mask:** Drop an semi-transparent UI overlay layer on top of your editing timeline to preview platform UI elements during composition.
- [ ] **Feed Grid Check (Instagram):** Ensure the primary focal point fits inside a centered $1080 \times 1080$ square for grid previews.
- [ ] **Text Wrapping Check:** Verify no caption text extends within 160 px of the right screen edge.
- [ ] **Final Clean Export:** Hide or disable the template UI overlay layer prior to rendering/exporting your final file.