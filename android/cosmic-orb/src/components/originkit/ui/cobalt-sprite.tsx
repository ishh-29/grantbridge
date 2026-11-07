/* eslint-disable */
// Delivered by Originkit · stack: nextjs · styling: tailwind
"use client"
import { useEffect, useRef, useState } from "react"
import type { CSSProperties } from "react"

/* ------------------------------------------------------------------ *
 *  MarbleSprite
 *  A sky-blue sprite with two pill eyes, sealed in a thick glass
 *  capsule: the upper half crystal clear, the lower half frosted, the
 *  two halves meeting at a tilted seam whose glass lip reads as a
 *  banded ellipse. The sprite turns to look at the cursor and blinks;
 *  the capsule leans toward it while the studio highlights stay put.
 *
 *  Built after a still render of a blue character in a glass capsule
 *  on black (no source code, so this is a match to the picture, not a
 *  port). Every default below was measured off that image, in units
 *  of the shell's radius (383px in a 1080px frame):
 *
 *    shell      centre of frame, diameter 0.709 of the shorter side
 *    sprite     concentric, r 0.593
 *    seam       plane normal (0.516, 0.736, 0.438), offset -0.04 -
 *               fitted to 20 points on the lip, the lower arc in
 *               front of the sprite and the upper arc behind it
 *    face       looking 12.4deg right, 10.1deg up, rolled -10deg;
 *               the pills sit 22.5deg either side of that axis
 *    highlights five studio reflections on the dome at r 0.83-0.89,
 *               from 93deg round to 33deg, each stretched along the rim
 *
 *  One fragment shader, ray traced per pixel, orthographic:
 *
 *    1. the shell refracts (n 1.5) twice. For a concentric shell a
 *       ray's distance from the centre is invariant, so the sprite
 *       keeps its true size, and every ray beyond the inner radius is
 *       totally internally reflected - that is the bright band inside
 *       the silhouette, not a painted rim
 *    2. the studio is stored as a mirror-ball map: a reflected
 *       direction R is drawn at normalize(R + view).xy, which is the
 *       exact spot a front-surface reflection of R lands on a unit
 *       sphere. So the measured highlight shapes are painted straight
 *       into it, and every other surface (the sprite, the inside of
 *       the back wall, the tilted capsule) samples the same studio
 *    3. the frosted half scatters: what is behind it is blurred to a
 *       soft blue glow, and it brightens with the path length through
 *       it toward the silhouette, most on the side the key light hits
 *    4. the seam lip is an annulus on the cut plane, its edges drawn
 *       as glass lines a constant number of pixels wide
 *    5. the sprite is satin: a wrapped diffuse, a broad sheen from the
 *       big top-right softbox, and the studio blurred by its roughness.
 *       The pills are raised half-cylinders bent onto its surface.
 * ------------------------------------------------------------------ */

/* ----------------------------------------------------------- defaults */

const DEFAULTS = {
    face: "eyes",
    background: "#000000",
    scale: 90,
    spriteColor: "#1400F6",
    frost: 5,
    follow: "frame",
    reach: 10,
    lean: 10,
    blink: 10,
    float: 15,
}

const DEFAULT_ADVANCED = {
    /** Where the sprite looks with no cursor - the reference's own gaze */
    restX: 12,
    restY: 10,
    /** Roll of the face about its own axis; negative is clockwise */
    roll: -10,
    /** Hard limit on how far it turns toward the cursor */
    maxTurn: 38,
    /** Direction the seam plane faces, in the picture plane (0 = right, 90 = up) */
    seamAngle: 55,
    /** How far the seam plane is turned away from facing the camera */
    seamTilt: 64,
    /** Seam plane's distance from the centre, % of the shell radius; negative is toward the frosted half */
    seamOffset: -5,
    /** Shell wall, % of its radius */
    shell: 4.5,
    /** How far the seam's lip reaches in past the wall, % of the radius */
    lip: 6,
    /** Sprite radius, % of the shell's */
    spriteSize: 59.3,
    /** Angle between the pills, seen from the sprite's centre */
    eyeGap: 45,
    eyeLength: 34,
    eyeWidth: 10,
    eyeColor: "#F3F2F8",
    lightAngle: 0,
    gloss: 100,
    glow: 100,
    grain: 100,
    followMs: 90,
    blinkMs: 150,
}

type Advanced = typeof DEFAULT_ADVANCED

/* -------------------------------------------------------------- types */

export interface MarbleSpriteProps {
    /** Whether the sprite wears its pill eyes */
    face?: "eyes" | "none"
    /** Sits behind the capsule; the glass shows it through the clear half */
    background?: string
    /** Size of the capsule, in % of the reference's framing (100 = 71% of the frame's shorter side) */
    scale?: number
    /** Mid tone of the sprite; its lit and shadow sides are derived from it */
    spriteColor?: string
    /** 0-10 how milky the lower half of the capsule is; 0 is clear glass all round */
    frost?: number
    /** Follow the cursor anywhere on the page, only over the frame, or never */
    follow?: "page" | "frame" | "off"
    /** 0-10 how hard the sprite turns to look at the cursor */
    reach?: number
    /** 0-10 how far the capsule leans toward the cursor */
    lean?: number
    /** 0-10 how often it blinks; 0 never */
    blink?: number
    /** 0-10 slow bob and sway of the whole capsule */
    float?: number
    /** Tuning constants behind the look */
    advanced?: Partial<Advanced>
    style?: CSSProperties
}

/* ------------------------------------------------------------ shaders */

const VERT = `
attribute vec2 aPos;
void main() {
    gl_Position = vec4(aPos, 0.0, 1.0);
}
`

const FRAG = `
uniform vec2  uCenter;   // capsule centre, device px
uniform float uRadius;   // capsule radius, device px
uniform vec3  uSeamN;    // seam plane normal, view space, toward the clear half
uniform float uSeamD;
uniform float uRi;       // inner radius of the shell
uniform float uLip;      // inner radius of the seam lip
uniform vec3  uBallC;
uniform float uBallR;
uniform mat3  uRot;      // sprite local -> view
uniform vec4  uEye;      // half gap, half segment length, half width (rad), openness
uniform float uFace;
uniform vec3  uBall;
uniform vec3  uEyeCol;
uniform vec3  uBg;
uniform float uFrost;    // 0 clear, 1 the reference, 2 near opaque milk
uniform float uGloss;
uniform float uGlow;
uniform float uGrain;
uniform vec2  uLight;    // cos, sin of the studio's roll
uniform float uDpr;
uniform float uTime;

const float IOR = 1.5;

float hash13(vec3 p) {
    p = fract(p * 0.1031);
    p += dot(p, p.zyx + 31.32);
    return fract((p.x + p.y) * p.z);
}

/* ------------------------------------------------------------ studio */

// A soft stadium in mirror-ball space. blur widens it for rough
// surfaces and lowers its peak so the energy stays about the same.
float stad(vec2 m, vec2 c, float a, float hl, float hw, float blur) {
    vec2 d = m - c;
    float ca = cos(a), sa = sin(a);
    vec2 q = vec2(ca * d.x + sa * d.y, -sa * d.x + ca * d.y);
    q.x = max(abs(q.x) - hl, 0.0);
    float w = hw + blur;
    float k = length(q) / w;
    // a crisp core with a bloom skirt, as a photographed window reads
    float v = smoothstep(1.0, 0.6, k) * 0.8 + exp(-k * k * 0.9) * 0.2;
    return v * (hw / w) * ((hl + hw) / (hl + w));
}

vec2 polar(float r, float deg) {
    float a = radians(deg);
    return r * vec2(cos(a), sin(a));
}

/* The reference's studio, painted where its reflections land on the
   front of a unit sphere: each light's centre, half length and half
   width are the measured blob, in shell radii (widened by the blur the
   picture's bloom put on them). ring scales the bright surround, upper
   the three lights along the top; mz pulls the map in toward the centre
   (see shadeBall). */
vec3 env(vec3 R, float blur, float ring, float mz, float upper) {
    vec3 h = R + vec3(0.0, 0.0, 1.0);
    float lh = length(h);
    vec2 m = lh > 1e-4 ? h.xy / lh : normalize(R.xy + 1e-6);
    m *= mz;
    m = vec2(uLight.x * m.x + uLight.y * m.y, -uLight.y * m.x + uLight.x * m.y);
    float rm = length(m);

    // All five lights sit in the top right, inside x > -0.25, y > 0.25;
    // 0.3 past that their bloom is below a thousandth of a level, so most
    // directions skip the lot
    vec3 c = vec3(0.0);
    float mg = 0.3 + blur * 3.0;
    if (m.x > -0.25 - mg && m.y > 0.25 - mg) {
        float s = 0.0;
        s += stad(m, polar(0.884, 92.7), radians(161.0), 0.040, 0.024, blur) * upper;
        s += stad(m, polar(0.839, 73.1), radians(149.0), 0.130, 0.040, blur) * upper;
        s += stad(m, polar(0.892, 61.1), radians(144.0), 0.145, 0.033, blur) * upper;
        s += stad(m, polar(0.884, 33.4), radians(120.0), 0.160, 0.036, blur) * 0.9;
        s += stad(m, polar(0.825, 34.2), radians(116.0), 0.105, 0.040, blur);
        c = vec3(1.0, 0.99, 0.98) * 30.0 * s;
    }

    // the bright surround behind the capsule: every grazing view of the
    // glass picks it up, which is the white rim all round the reference
    c += vec3(0.93, 0.95, 1.0) * 3.2 * smoothstep(0.982, 0.999, rm) * ring;
    // a broad dim softbox overhead, so the dark dome is never a hole
    c += vec3(0.9, 0.93, 1.0) * 0.05 * smoothstep(-0.2, 0.9, m.y) * (1.0 - rm * rm * 0.5);
    return c;
}

float fres(float c) {
    c = clamp(c, 0.0, 1.0);
    return 0.04 + 0.96 * pow(1.0 - c, 5.0);
}

/* ------------------------------------------------------------ frost */

// How brightly the frosted half glows at P, a point on its wall. It is
// a lampshade: lit from outside, it glows where the lights are behind it.
// The key sits low on the left in front (ext weights it - the far wall
// barely sees it), a second light low on the right behind. A third, up
// by the camera, comes in through the clear dome, and the sprite stands
// in its way: the navy crescent tucked under its lower right.
float frostLight(vec3 P, float ext) {
    vec3 n = normalize(P);
    float kl = max(dot(n, normalize(vec3(-0.95, -0.15, 0.30))), 0.0);
    float kb = max(dot(n, normalize(vec3(0.55, -0.60, -0.60))), 0.0);
    vec3 Lo = normalize(vec3(-0.10, 0.15, 0.98));
    vec3 oc = uBallC - P;
    float tc = max(dot(oc, Lo), 0.0);
    float dist = length(oc - Lo * tc);
    float shade = smoothstep(uBallR * 0.95, uBallR * 1.12, dist);
    return 0.02 + ext * 1.1 * kl * kl * kl + (0.85 * kb * kb + 0.05) * shade;
}

/* -------------------------------------------------------------- ball */

vec2 sphereHit(vec3 ro, vec3 rd, vec3 c, float r) {
    vec3 oc = ro - c;
    float b = dot(oc, rd);
    float h = b * b - (dot(oc, oc) - r * r);
    if (h < 0.0) return vec2(-1.0);
    h = sqrt(h);
    return vec2(-b - h, -b + h);
}

// One pill in the sprite's local frame: q is east/north in radians
// round its centre. Returns coverage and the outward bend of the normal.
vec4 pill(vec2 q, float px) {
    float open = max(uEye.w, 0.12);
    float hl = uEye.y * open;
    float hw = uEye.z * mix(0.7, 1.0, open);
    vec2 a = vec2(q.x, max(abs(q.y) - hl, 0.0) * sign(q.y));
    // a closing pill squashes into a flat dash, not a shrinking one
    a.y /= mix(0.45, 1.0, open);
    float dd = length(a);
    float cov = smoothstep(hw + px, hw - px, dd);
    float hgt = sqrt(max(hw * hw - dd * dd, 0.0));
    vec2 dir = dd > 1e-5 ? a / dd : vec2(0.0);
    return vec4(cov, dir * dd, hgt);
}

vec3 shadeBall(vec3 P, vec3 rd, float px) {
    vec3 N = normalize(P - uBallC);
    vec3 nl = N * uRot;
    vec3 albedo = uBall;
    float eye = 0.0;
    vec3 Ns = N;

    // only the cap round the face can hold a pill: skip the trig elsewhere
    if (uFace > 0.5 && nl.z > cos(min(uEye.x + uEye.y + uEye.z + 0.05, 3.0))) {
        float lon = atan(nl.x, nl.z);
        float lat = asin(clamp(nl.y, -1.0, 1.0));
        float cl = cos(lat);
        float pa = px / uBallR * 1.2;
        float side = lon < 0.0 ? -1.0 : 1.0;
        vec2 q = vec2((lon - side * uEye.x) * cl, lat);
        vec4 e = pill(q, pa);
        if (e.x > 0.0) {
            // east and north on the sphere, in local space
            vec3 tu = vec3(cos(lon), 0.0, -sin(lon));
            vec3 tv = vec3(-sin(lat) * sin(lon), cl, -sin(lat) * cos(lon));
            vec3 bent = normalize(nl * max(e.w, 1e-4) + (tu * e.y + tv * e.z) * 0.85);
            Ns = normalize(uRot * bent);
            eye = e.x;
            albedo = mix(albedo, uEyeCol, e.x);
        }
    }

    vec3 n = normalize(mix(N, Ns, eye));
    // Flat, heavily wrapped diffuse: the frosted bowl fills the shadow
    // side, so the reference's sprite only drops to ~0.8 of its mid tone
    vec3 Lk = normalize(vec3(0.62, 0.62, 0.48));
    float d = clamp((dot(n, Lk) + 0.6) / 1.6, 0.0, 1.0);
    vec3 c = albedo * (0.80 + 0.30 * d);
    // satin sheen: the reference's sprite is saturated straight on and
    // whitens toward its rim on the lit side (up and right), not across
    // the middle - a grazing-angle lift, as velvety plastic does
    float rimLift = pow(1.0 - clamp(n.z, 0.0, 1.0), 1.6) *
                    smoothstep(-0.5, 0.7, dot(n.xy, vec2(0.55, 0.83)));
    c += vec3(0.30, 0.31, 0.29) * rimLift * (1.0 - eye);
    // and the big softbox up and right washes that whole side pale
    float wash = pow(max(dot(n, normalize(vec3(0.62, 0.62, 0.35))), 0.0), 1.5);
    c += vec3(0.45, 0.46, 0.42) * wash * (1.0 - eye);
    // the pills keep a broad lobe: they are glossier than the body
    c += vec3(0.30) * pow(max(dot(n, normalize(vec3(0.58, 0.50, 0.64))), 0.0), 2.2) * eye;
    // studio reflection, blurred by the satin's roughness
    vec3 R = reflect(rd, n);
    float F = 0.04 + 0.96 * pow(1.0 - max(dot(-rd, n), 0.0), 5.0);
    // The reference's highlights sit at 0.75 of the sprite's radius, not
    // at the 0.86 an orthographic mirror would put them: its camera is
    // perspective, close enough that the sprite sees the studio wider.
    // And only the right-hand pair shows on it, as two soft streaks by
    // the right eye; the top three are lost in its pale lit crown.
    c += env(R, mix(0.06, 0.04, eye), 0.10, 1.15, 0.15) * mix(F * 1.2, F * 1.8 + 0.03, eye) * uGloss;
    // the pills are pale but not paper: their shade side cools to lilac
    c = mix(c, c * vec3(0.86, 0.87, 1.0), eye * (1.0 - d));
    return c;
}

/* --------------------------------------------------------- back wall */

vec3 backWall(vec3 Pw, vec3 rd, float px) {
    vec3 Nin = -Pw / uRi;
    float side = dot(uSeamN, Pw) - uSeamD;
    float fm = smoothstep(0.012, -0.012, side) * min(uFrost, 1.0);

    // clear: the room behind the capsule, plus the inner surface's own
    // concave reflection of the studio
    float F = fres(dot(-rd, Nin));
    vec3 clear = uBg * 0.85 + env(reflect(rd, Nin), 0.02, 0.4, 1.0, 1.0) * F * 0.55 * uGloss;
    // smoky toward the rim: the far wall seen ever more edge on
    float g = smoothstep(0.25, 0.8, 1.0 - abs(dot(rd, Nin)));
    clear += vec3(0.003, 0.0035, 0.005) + vec3(0.040, 0.042, 0.052) * g * g;

    // frosted: seen from inside, lit as the rest of the bowl is
    if (fm <= 0.0) return clear;
    vec3 frosted = vec3(0.84, 0.88, 0.97) * 0.42 * frostLight(Pw, 0.25);
    return mix(clear, frosted, fm);
}

/* -------------------------------------------------------------- seam */

// The lip of the seam: an annulus on the cut plane from uLip out to the
// shell. s runs 0 at its inner edge to 1 at the shell's outer surface.
vec4 seamBand(vec2 p, float px) {
    if (abs(uSeamN.z) < 1e-3) return vec4(0.0, 0.0, -9.0, 0.0);
    float zp = (uSeamD - uSeamN.x * p.x - uSeamN.y * p.y) / uSeamN.z;
    vec3 P = vec3(p, zp);
    float rp = length(P);
    if (rp < uLip - 0.02 || rp > 1.0) return vec4(0.0, 0.0, zp, 0.0);
    vec2 g = (P.xy - P.z * uSeamN.xy / uSeamN.z) / max(rp, 1e-4);
    float sw = 1.0 - uLip;
    float s = (rp - uLip) / sw;
    float ds = length(g) * px / sw; // s per device pixel
    float body = smoothstep(-ds, ds, s) * smoothstep(1.0 + ds, 1.0 - ds, s);
    // the glass edges: bright where the faces meet, a dark refracted
    // line beside each
    float w = max(1.3 * ds, 0.07);
    float lines = 0.0;
    lines += 1.00 * smoothstep(max(1.8 * ds, 0.14), 0.0, abs(s - 0.90));
    lines += 0.70 * smoothstep(w, 0.0, abs(s - 0.50));
    lines += 0.85 * smoothstep(w, 0.0, abs(s - 0.08));
    float dark = 0.0;
    dark += smoothstep(w * 1.3, 0.0, abs(s - 0.70));
    dark += smoothstep(w * 1.1, 0.0, abs(s - 0.29));
    return vec4(body, clamp(lines, 0.0, 1.0), zp, clamp(dark, 0.0, 1.0));
}

/* -------------------------------------------------------------- main */

float tone(float x) {
    return x < 0.8 ? x : 0.8 + 0.2 * (1.0 - exp(-(x - 0.8) / 0.2));
}

void main() {
    float px = 1.0 / uRadius;
    vec2 p = (gl_FragCoord.xy - uCenter) * px;
    float r = length(p);
    vec3 rd = vec3(0.0, 0.0, -1.0);

    // bloom round the silhouette, measured off the reference: a tight
    // core and a wider skirt
    float x = max(r - 1.0, 0.0);
    vec3 halo = vec3(0.92, 0.95, 1.0) * (0.11 * exp(-x / 0.006) + 0.03 * exp(-x / 0.02)) * uGlow;

    vec3 col = uBg;
    float cov = 1.0 - smoothstep(1.0 - px, 1.0 + px, r);
    if (cov > 0.0) {
        float rr = min(r, 0.99999);
        vec3 P0 = vec3(p, sqrt(1.0 - rr * rr));
        vec3 N0 = P0;
        float Fo = fres(N0.z);
        vec3 refl = env(reflect(rd, N0), 0.0, 1.0, 1.0, 1.0) * Fo * uGloss;
        float frontSide = dot(uSeamN, P0) - uSeamD;
        float fm = smoothstep(0.012, -0.012, frontSide) * min(uFrost, 1.0);
        // past the reference the frost thickens: milk spreads inward
        float thick = max(uFrost - 1.0, 0.0);

        vec3 r1 = refract(rd, N0, 1.0 / IOR);
        vec2 hi = sphereHit(P0, r1, vec3(0.0), uRi);
        vec3 Pi = P0 + r1 * hi.x;
        vec3 Ni = Pi / uRi;
        vec3 r2 = refract(r1, Ni, IOR);
        vec3 inner;
        float ballZ = -9.0;
        float tir = 1.0 - step(0.0, hi.x) * step(1e-4, dot(r2, r2));

        if (tir < 0.5) {
            // into the cavity: the sprite, or the far wall
            vec2 hb = sphereHit(Pi, r2, uBallC, uBallR);
            if (hb.x > 0.0) {
                vec3 Pb = Pi + r2 * hb.x;
                ballZ = Pb.z;
                inner = shadeBall(Pb, r2, px);
            } else {
                vec2 hw = sphereHit(Pi, r2, vec3(0.0), uRi);
                inner = backWall(Pi + r2 * hw.y, r2, px);
            }
            // glass tint through two walls
            inner *= vec3(0.96, 0.975, 0.985);

            // frosted front: the cavity blurs into a soft glow
            if (fm > 0.0) {
                vec3 oc = uBallC - Pi;
                float tc = max(dot(oc, r2), 0.0);
                float dist = length(oc - r2 * tc);
                float bc = smoothstep(uBallR + 0.24, uBallR - 0.22, dist);
                vec3 behind = mix(inner * 0.35, uBall * 0.60, bc);
                // straight on, frost only softens; toward the rim the path
                // through it grows and it turns to milk - measured, it
                // climbs from a tenth to full between r 0.78 and 0.97
                float milk = pow(smoothstep(0.80 + 0.2 * thick, 0.22, N0.z), 1.8 - 1.0 * thick);
                float sharp = smoothstep(0.75, 0.95, N0.z) * (1.0 - thick);
                behind = mix(behind, inner, sharp * 0.3);
                // the milk glows all round the bowl's rim, the lights only
                // tint how brightly
                float scatter = (0.55 + frostLight(P0, 0.85)) * (0.02 + 0.98 * milk);
                vec3 frosted = behind * (1.0 - milk * 0.8) + vec3(0.88, 0.90, 0.97) * scatter;
                inner = mix(inner, frosted, fm);
            }
        } else {
            // totally internally reflected inside the wall: the ray runs
            // round the glass and leaves through the outer surface
            vec3 rt = reflect(r1, normalize(Pi));
            if (hi.x <= 0.0) rt = r1;
            vec2 ho = sphereHit(P0 + r1 * max(hi.x, 0.0), rt, vec3(0.0), 1.0);
            vec3 P2 = P0 + r1 * max(hi.x, 0.0) + rt * ho.y;
            vec3 r3 = refract(rt, -normalize(P2), IOR);
            if (dot(r3, r3) < 1e-4) r3 = rt;
            // clear: a smoky grey band with a bright line where it
            // starts - the inner surface seen edge on
            float b = (r - uRi) / (1.0 - uRi);
            vec3 clearRim = uBg * 0.6 + env(r3, 0.03, 0.05, 1.0, 1.0) * 0.20 + vec3(0.040, 0.042, 0.052) * (0.8 + 0.6 * b);
            // the line is brightest where the overhead softbox feeds it
            clearRim += vec3(0.9, 0.93, 1.0) * 0.6 * exp(-pow(b / 0.12, 2.0)) * smoothstep(-0.1, 0.8, p.y);
            inner = clearRim;
            if (fm > 0.0) {
                vec3 frostRim = vec3(0.88, 0.90, 0.97) * (0.55 + frostLight(P0, 0.85)) * 1.15;
                inner = mix(clearRim, frostRim, fm);
            }
        }

        col = inner * (1.0 - Fo) + refl;

        // the seam's lip, in front of or behind the sprite
        vec4 sb = seamBand(p, px);
        if (sb.x > 0.0 && sb.z > ballZ) {
            float hidden = sb.z < 0.0 ? fm * 0.85 : 0.0;
            float a = sb.x * (1.0 - hidden);
            vec3 edge = vec3(0.95, 0.97, 1.0) * 1.6;
            // the lip is the cut face of the glass - milky where it is
            // the frosted half's - so it reads as a pale solid body
            vec3 c2 = col * 0.62 + vec3(0.12, 0.125, 0.15) * (0.6 + 0.6 * min(uFrost, 1.0));
            c2 = mix(c2, c2 * 0.35, sb.w * 0.8);
            c2 = mix(c2, edge, sb.y);
            col = mix(col, c2, a);
        }
    }

    col = mix(uBg + halo, col, cov);

    col = vec3(tone(col.r), tone(col.g), tone(col.b));
    col = pow(clamp(col, 0.0, 1.0), vec3(1.0 / 2.2));
    // film grain at a fixed size in CSS pixels, like the reference's
    vec2 gp = floor(gl_FragCoord.xy / max(uDpr, 1.0));
    col += (hash13(vec3(gp, uTime)) - 0.5) * (4.0 / 255.0) * uGrain;
    gl_FragColor = vec4(col, 1.0);
}
`

/* ------------------------------------------------------------- helpers */

let parseCtx: CanvasRenderingContext2D | null | undefined

/** CSS colour string -> normalised sRGB triple. */
function toRGB(css: string): [number, number, number] {
    if (!css) return [0, 0, 0]
    const s = css.trim()
    const hex = /^#([0-9a-f]{3,8})$/i.exec(s)
    if (hex) {
        let h = hex[1]
        if (h.length === 3 || h.length === 4) {
            h = h
                .split("")
                .map((c) => c + c)
                .join("")
        }
        const n = parseInt(h.slice(0, 6), 16)
        return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]
    }
    const fn = /^rgba?\(([^)]+)\)$/i.exec(s)
    if (fn) {
        const v = fn[1]
            .split(/[\s,/]+/)
            .filter(Boolean)
            .slice(0, 3)
            .map((x) => (x.indexOf("%") >= 0 ? parseFloat(x) * 2.55 : parseFloat(x)))
        return [(v[0] || 0) / 255, (v[1] || 0) / 255, (v[2] || 0) / 255]
    }
    // named colours, hsl(), oklch() ... let the browser resolve it
    if (typeof document !== "undefined") {
        if (parseCtx === undefined) parseCtx = document.createElement("canvas").getContext("2d")
        if (parseCtx) {
            parseCtx.fillStyle = "#000000"
            parseCtx.fillStyle = s
            const out = parseCtx.fillStyle
            if (typeof out === "string" && out.charAt(0) === "#" && out !== s) return toRGB(out)
        }
    }
    return [0, 0, 0]
}

/** sRGB -> linear, the shader lights in linear space */
function lin(css: string): [number, number, number] {
    const c = toRGB(css)
    return [Math.pow(c[0], 2.2), Math.pow(c[1], 2.2), Math.pow(c[2], 2.2)]
}

function compile(gl: WebGLRenderingContext, type: number, src: string): WebGLShader | null {
    const sh = gl.createShader(type)
    if (!sh) return null
    gl.shaderSource(sh, src)
    gl.compileShader(sh)
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        gl.deleteShader(sh)
        return null
    }
    return sh
}

type V3 = [number, number, number]

function rotX(v: V3, a: number): V3 {
    const c = Math.cos(a), s = Math.sin(a)
    return [v[0], c * v[1] - s * v[2], s * v[1] + c * v[2]]
}

function rotY(v: V3, a: number): V3 {
    const c = Math.cos(a), s = Math.sin(a)
    return [c * v[0] + s * v[2], v[1], -s * v[0] + c * v[2]]
}

const DEG = Math.PI / 180
/** Capsule diameter at Scale 100, as a share of the frame's shorter side - measured off the reference (766px in 1080). */
const FIT = 0.709
const DPR_CAP = 2
/** Most device px drawn across the capsule's diameter, whatever the screen. */
const CAPSULE_PX = 1600

/* ----------------------------------------------------------- component */

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 * @framerIntrinsicWidth 1080
 * @framerIntrinsicHeight 1080
 */
export default function MarbleSprite({
    face = DEFAULTS.face,
    background = DEFAULTS.background,
    scale = DEFAULTS.scale,
    spriteColor = DEFAULTS.spriteColor,
    frost = DEFAULTS.frost,
    follow = DEFAULTS.follow,
    reach = DEFAULTS.reach,
    lean = DEFAULTS.lean,
    blink = DEFAULTS.blink,
    float = DEFAULTS.float,
    advanced,
    style,
}: MarbleSpriteProps) {
    const hostRef = useRef<HTMLDivElement>(null)
    const canvasRef = useRef<HTMLCanvasElement>(null)
    const [failed, setFailed] = useState(false)

    // Live prop mirror: the render loop reads this, so a control change
    // never tears down the GL context.
    const props = {
        face,
        background,
        scale,
        spriteColor,
        frost,
        follow,
        reach,
        lean,
        blink,
        float,
        adv: { ...DEFAULT_ADVANCED, ...advanced },
    }
    const propsRef = useRef(props)
    propsRef.current = props

    useEffect(() => {
        const host = hostRef.current
        const canvas = canvasRef.current
        if (!host || !canvas) return

        let disposed = false
        let raf = 0
        let gl: WebGLRenderingContext | null = null
        let program: WebGLProgram | null = null
        let buffer: WebGLBuffer | null = null
        let uni: Record<string, WebGLUniformLocation | null> = {}
        let onScreen = true
        let pageVisible = true
        let reduceMotion = false

        // The frame's size in CSS px comes from the ResizeObserver only. The
        // loop never reads layout: inside an editor whose panel is changing
        // the page every frame, one layout read per frame is a forced reflow
        // per frame, and that is what made the follow stutter.
        let cssW = Math.max(1, host.clientWidth)
        let cssH = Math.max(1, host.clientHeight)
        let dpr = 1
        // Share of full resolution, lowered when the GPU falls behind
        let quality = 1

        // Raw client coordinates from the events; turned into a 0-1 share
        // of the frame once per frame, against the box as displayed (so it
        // holds at any canvas zoom or parent scale). May run past 0-1 in
        // page mode.
        const pointer = { x: 0, y: 0, u: 0.5, v: 0.5, active: false, down: false, moved: false, lastMove: -1e9 }
        let rectDirty = true

        // eased state
        let yaw = DEFAULT_ADVANCED.restX * DEG
        let pitch = DEFAULT_ADVANCED.restY * DEG
        let leanX = 0
        let leanY = 0
        let open = 1
        let squint = 0
        let nextBlink = 1.6
        let blinkT = -1
        let doubleBlink = false
        let clock = 0
        let lastNow = 0

        // pacing
        let lastDraw = -1e9
        let drawnProps: unknown = null
        let forceDraw = true
        let frameMs = 16.7
        let postDrawMs = 16.7
        let slowFor = 0
        let fastFor = 0
        let justDrew = false

        // reused every frame - no garbage in the loop
        const rot = new Float32Array(9)
        const colorCache = new Map<string, [number, number, number]>()
        const linC = (css: string) => {
            let c = colorCache.get(css)
            if (!c) {
                if (colorCache.size > 32) colorCache.clear()
                c = lin(css)
                colorCache.set(css, c)
            }
            return c
        }

        /* ------------------------------------------------------ setup */

        function init(): boolean {
            const ctx = canvas!.getContext("webgl", {
                alpha: false,
                antialias: false,
                depth: false,
                stencil: false,
                // an ornament on a page should never wake a laptop's discrete GPU
                powerPreference: "low-power",
            }) as WebGLRenderingContext | null
            if (!ctx) return false
            gl = ctx
            const hp = gl.getShaderPrecisionFormat(gl.FRAGMENT_SHADER, gl.HIGH_FLOAT)
            const prelude = "precision " + (hp && hp.precision > 0 ? "highp" : "mediump") + " float;\n"
            const vs = compile(gl, gl.VERTEX_SHADER, VERT)
            const fs = compile(gl, gl.FRAGMENT_SHADER, prelude + FRAG)
            if (!vs || !fs) return false
            const prog = gl.createProgram()
            if (!prog) return false
            gl.attachShader(prog, vs)
            gl.attachShader(prog, fs)
            gl.bindAttribLocation(prog, 0, "aPos")
            gl.linkProgram(prog)
            gl.deleteShader(vs)
            gl.deleteShader(fs)
            if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return false
            program = prog
            gl.useProgram(prog)

            buffer = gl.createBuffer()
            gl.bindBuffer(gl.ARRAY_BUFFER, buffer)
            gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
            gl.enableVertexAttribArray(0)
            gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0)

            uni = {}
            for (const n of [
                "uCenter", "uRadius", "uSeamN", "uSeamD", "uRi", "uLip", "uBallC", "uBallR", "uRot",
                "uEye", "uFace", "uBall", "uEyeCol", "uBg", "uFrost", "uGloss", "uGlow", "uGrain",
                "uLight", "uDpr", "uTime",
            ])
                uni[n] = gl.getUniformLocation(prog, n)
            forceDraw = true
            return true
        }

        /** Size the drawing buffer; true when it changed. */
        function applySize(): boolean {
            if (!gl) return false
            const p = propsRef.current
            const device = Math.min(window.devicePixelRatio || 1, DPR_CAP)
            // Cap the pixels across the capsule: a full-bleed hero on a 2x
            // screen then costs what a mid-size one does. Glass this smooth
            // looks the same either side of the cap; the GPU does not.
            const diam = FIT * (Math.max(1, p.scale) / 100) * Math.min(cssW, cssH)
            const budget = diam > 0 ? CAPSULE_PX / diam : device
            dpr = Math.max(0.5, Math.min(device, budget) * quality)
            const w = Math.max(1, Math.round(cssW * dpr))
            const h = Math.max(1, Math.round(cssH * dpr))
            if (canvas!.width === w && canvas!.height === h) return false
            canvas!.width = w
            canvas!.height = h
            gl.viewport(0, 0, w, h)
            return true
        }

        /* ------------------------------------------------------ state */

        /** Advance the animation; returns how often it needs drawing. */
        function step(dt: number, now: number): "active" | "idle" | "still" {
            const p = propsRef.current
            const a = p.adv
            const still = reduceMotion
            clock += dt

            // capsule geometry in CSS px - the state is resolution free
            const radius = FIT * (Math.max(1, p.scale) / 100) * Math.min(cssW, cssH) * 0.5
            const fl = still ? 0 : p.float / 10
            const cx = cssW * 0.5 + Math.sin(clock * 0.53) * fl * 0.035 * radius
            const cy = cssH * 0.5 + Math.sin(clock * 0.8) * fl * 0.07 * radius

            // one layout read, and only while the cursor moves or the page scrolled
            if (pointer.active && (pointer.moved || rectDirty)) {
                const r = host!.getBoundingClientRect()
                if (r.width > 0 && r.height > 0) {
                    pointer.u = (pointer.x - r.left) / r.width
                    pointer.v = (pointer.y - r.top) / r.height
                }
                pointer.moved = false
                rectDirty = false
            }

            /* where the sprite looks, and where the capsule leans */
            let tx = a.restX * DEG
            let ty = a.restY * DEG
            let lx = 0
            let ly = 0
            const following = p.follow !== "off" && pointer.active
            if (following) {
                // cursor in capsule radii, on a plane D radii in front of
                // it: a nearer plane is a harder turn
                const dx = (pointer.u * cssW - cx) / radius
                const dy = -(pointer.v * cssH - cy) / radius
                if (p.reach > 0) {
                    const D = 16 / p.reach
                    const lim = a.maxTurn * DEG
                    tx = Math.max(-lim, Math.min(lim, Math.atan2(dx, D)))
                    ty = Math.max(-lim, Math.min(lim, Math.atan2(dy, Math.hypot(dx, D))))
                }
                const k = (p.lean / 10) * 22 * DEG
                lx = Math.max(-1, Math.min(1, dx / 2.5)) * k
                ly = Math.max(-1, Math.min(1, dy / 2.5)) * k
            } else if (!still) {
                // idle: a slow look round, as if it were curious
                tx += Math.sin(clock * 0.37) * 6 * DEG * fl + Math.sin(clock * 0.91) * 2 * DEG * fl
                ty += Math.sin(clock * 0.29 + 1.3) * 4 * DEG * fl
            }
            if (!still) {
                // the capsule sways a little on its own
                lx += Math.sin(clock * 0.53) * 3 * DEG * fl
                ly += Math.sin(clock * 0.41 + 0.7) * 2 * DEG * fl
            }
            const y0 = yaw, p0 = pitch, lx0 = leanX, ly0 = leanY
            const k = 1 - Math.exp(-dt / Math.max(0.005, a.followMs / 1000))
            yaw += (tx - yaw) * k
            pitch += (ty - pitch) * k
            // the glass is heavier than the sprite: it leans on a longer ease
            const kl = 1 - Math.exp(-dt / 0.35)
            leanX += (lx - leanX) * kl
            leanY += (ly - leanY) * kl

            /* blink: shut fast, open a little slower, now and then twice */
            const bd = Math.max(0.04, a.blinkMs / 1000)
            if (!still && p.blink > 0) {
                nextBlink -= dt
                if (nextBlink <= 0 && blinkT < 0) {
                    blinkT = 0
                    const gap = (11 - p.blink) * (0.5 + Math.random())
                    if (doubleBlink) doubleBlink = false
                    else doubleBlink = Math.random() < 0.25
                    nextBlink = doubleBlink ? bd + 0.12 : gap
                }
            }
            let o = 1
            if (blinkT >= 0) {
                blinkT += dt
                const u = blinkT / bd
                o = u < 0.4 ? 1 - u / 0.4 : Math.min(1, (u - 0.4) / 0.6)
                if (u >= 1) blinkT = -1
            }
            // a press is a happy squint, held while the button is down
            const sq = pointer.down ? 1 : 0
            squint += (sq - squint) * (1 - Math.exp(-dt / 0.06))
            open = Math.min(o, 1 - squint * 0.8)

            // How fast the surface is moving, in px/s: a turn of x radians
            // moves the sprite's face about x radii. Fast wants 60 fps; slow
            // drift and the tail of a settle look the same at 30; within a
            // quarter pixel of rest there is nothing left to draw.
            const turn = Math.abs(yaw - y0) + Math.abs(pitch - p0) + Math.abs(leanX - lx0) + Math.abs(leanY - ly0)
            const speed = (turn / Math.max(dt, 1e-3)) * radius
            if (speed > 12 || blinkT >= 0 || Math.abs(sq - squint) > 1e-3 || now - pointer.lastMove < 300)
                return "active"
            const rest = (Math.abs(tx - yaw) + Math.abs(ty - pitch) + Math.abs(lx - leanX) + Math.abs(ly - leanY)) * radius
            return fl > 0 || rest > 0.25 ? "idle" : "still"
        }

        /* ------------------------------------------------------ frame */

        function draw() {
            if (!gl || !program) return
            const p = propsRef.current
            const a = p.adv
            const still = reduceMotion

            const W = canvas!.width
            const H = canvas!.height
            const radius = FIT * (Math.max(1, p.scale) / 100) * Math.min(W, H) * 0.5
            const fl = still ? 0 : p.float / 10
            const cx = W * 0.5 + Math.sin(clock * 0.53) * fl * 0.035 * radius
            const cy = H * 0.5 + Math.sin(clock * 0.8) * fl * 0.07 * radius

            /* sprite: local -> view, columns right, up, forward */
            const cp = Math.cos(pitch)
            const fx = Math.sin(yaw) * cp, fy = Math.sin(pitch), fz = Math.cos(yaw) * cp
            const rl = Math.hypot(fz, fx) || 1
            const rx = fz / rl, rz = -fx / rl
            // up = forward x right (right has no y)
            const ux = fy * rz, uy = fz * rx - fx * rz, uz = -fy * rx
            const cr = Math.cos(a.roll * DEG), sr = Math.sin(a.roll * DEG)
            rot[0] = rx * cr + ux * sr
            rot[1] = uy * sr
            rot[2] = rz * cr + uz * sr
            rot[3] = ux * cr - rx * sr
            rot[4] = uy * cr
            rot[5] = uz * cr - rz * sr
            rot[6] = fx
            rot[7] = fy
            rot[8] = fz

            /* seam plane, leaned toward the cursor */
            const sa = a.seamAngle * DEG
            const st = a.seamTilt * DEG
            let n: V3 = [Math.cos(sa) * Math.sin(st), Math.sin(sa) * Math.sin(st), Math.cos(st)]
            n = rotY(n, leanX)
            n = rotX(n, -leanY)

            const ri = 1 - Math.max(0.01, Math.min(0.3, a.shell / 100))
            const lip = Math.max(0.3, ri - Math.max(0, a.lip / 100))
            const br = Math.max(0.1, Math.min(ri - 0.02, a.spriteSize / 100))
            // the sprite bobs a touch out of step with the capsule
            const by = still ? 0 : Math.sin(clock * 0.8 - 0.9) * fl * 0.045

            gl.uniform2f(uni.uCenter, cx, H - cy)
            gl.uniform1f(uni.uRadius, radius)
            gl.uniform3f(uni.uSeamN, n[0], n[1], n[2])
            gl.uniform1f(uni.uSeamD, a.seamOffset / 100)
            gl.uniform1f(uni.uRi, ri)
            gl.uniform1f(uni.uLip, lip)
            gl.uniform3f(uni.uBallC, 0, by, 0)
            gl.uniform1f(uni.uBallR, br)
            gl.uniformMatrix3fv(uni.uRot, false, rot)
            gl.uniform4f(
                uni.uEye,
                (a.eyeGap / 2) * DEG,
                Math.max(0, (a.eyeLength - a.eyeWidth) / 2) * DEG,
                (a.eyeWidth / 2) * DEG,
                open
            )
            gl.uniform1f(uni.uFace, p.face === "eyes" ? 1 : 0)
            const bc = linC(p.spriteColor)
            const ec = linC(a.eyeColor)
            const bg = linC(p.background)
            gl.uniform3f(uni.uBall, bc[0], bc[1], bc[2])
            gl.uniform3f(uni.uEyeCol, ec[0], ec[1], ec[2])
            gl.uniform3f(uni.uBg, bg[0], bg[1], bg[2])
            gl.uniform1f(uni.uFrost, Math.max(0, Math.min(2, p.frost / 5)))
            gl.uniform1f(uni.uGloss, a.gloss / 100)
            gl.uniform1f(uni.uGlow, a.glow / 100)
            gl.uniform1f(uni.uGrain, a.grain / 100)
            gl.uniform2f(uni.uLight, Math.cos(a.lightAngle * DEG), Math.sin(a.lightAngle * DEG))
            gl.uniform1f(uni.uDpr, Math.max(dpr, 1))
            gl.uniform1f(uni.uTime, still ? 0 : clock % 100)

            gl.drawArrays(gl.TRIANGLES, 0, 3)
        }

        /* Drop resolution while frames run long, win it back once they run
           fast again. rAF's own interval right after a draw is the signal:
           a GPU that cannot keep up delays the next frame. */
        // ponytail: frame-time heuristic, not a GPU timer; EXT_disjoint_timer_query if it ever misjudges
        function adapt(ms: number) {
            postDrawMs += (ms - postDrawMs) * 0.1
            if (postDrawMs > 26) {
                slowFor += ms
                fastFor = 0
            } else if (postDrawMs < 19) {
                fastFor += ms
                slowFor = 0
            }
            if (slowFor > 600 && quality > 0.6) {
                quality = Math.max(0.6, quality * 0.85)
                slowFor = 0
                postDrawMs = 16.7
            } else if (fastFor > 4000 && quality < 1) {
                quality = Math.min(1, quality / 0.85)
                fastFor = 0
            }
        }

        function loop(now: number) {
            if (disposed) return
            raf = requestAnimationFrame(loop)
            if (!onScreen || !pageVisible) {
                lastNow = 0
                return
            }
            const ms = lastNow ? now - lastNow : 0
            lastNow = now
            if (ms > 0) {
                frameMs += (Math.min(ms, 100) - frameMs) * 0.1
                if (justDrew) adapt(ms)
            }
            justDrew = false
            const mode = step(Math.min(ms / 1000, 0.1), now)

            const p = propsRef.current
            const resized = applySize()
            const changed = forceDraw || resized || p !== drawnProps
            // 60 fps while it moves, 30 for the slow idle drift (its fastest
            // point covers a twelfth of a pixel a frame - 30 cannot be told
            // apart), none once settled. Half a frame of slack keeps the
            // cadence even on 90-144 Hz screens.
            const interval = changed ? 1000 / 60 : mode === "active" ? 1000 / 60 : mode === "idle" ? 1000 / 30 : Infinity
            if (now - lastDraw < interval - frameMs * 0.5) return
            lastDraw = now
            drawnProps = p
            forceDraw = false
            draw()
            justDrew = true
        }

        if (!init()) {
            setFailed(true)
            return
        }

        /* --------------------------------------------------- pointer */

        // Handlers only record; the work happens once per frame.
        const record = (e: PointerEvent) => {
            pointer.x = e.clientX
            pointer.y = e.clientY
            pointer.moved = true
            pointer.active = true
            pointer.lastMove = performance.now()
        }
        const onRootMove = (e: PointerEvent) => {
            if (propsRef.current.follow === "frame") record(e)
        }
        const onRootLeave = () => {
            if (propsRef.current.follow === "frame") {
                pointer.active = false
                pointer.lastMove = performance.now()
            }
            pointer.down = false
        }
        const onWinMove = (e: PointerEvent) => {
            if (propsRef.current.follow === "page") record(e)
        }
        const onWinOut = (e: PointerEvent) => {
            // cursor left the window entirely
            if (!e.relatedTarget && propsRef.current.follow === "page") {
                pointer.active = false
                pointer.lastMove = performance.now()
            }
        }
        const onDown = (e: PointerEvent) => {
            record(e)
            pointer.down = true
        }
        const onUp = (e: PointerEvent) => {
            pointer.down = false
            pointer.lastMove = performance.now()
            // a lifted finger ends the hover on touch
            if (e.pointerType === "touch") pointer.active = false
        }
        const onScroll = () => {
            rectDirty = true
        }
        const passive: AddEventListenerOptions = { passive: true }
        host.addEventListener("pointermove", onRootMove, passive)
        host.addEventListener("pointerleave", onRootLeave, passive)
        host.addEventListener("pointerdown", onDown, passive)
        window.addEventListener("pointermove", onWinMove, passive)
        window.addEventListener("pointerout", onWinOut, passive)
        window.addEventListener("pointerup", onUp, passive)
        window.addEventListener("pointercancel", onUp, passive)
        window.addEventListener("scroll", onScroll, { passive: true, capture: true })

        /* --------------------------------------------------- lifecycle */

        const ro =
            typeof ResizeObserver !== "undefined"
                ? new ResizeObserver((entries) => {
                      const r = entries[entries.length - 1].contentRect
                      cssW = Math.max(1, r.width)
                      cssH = Math.max(1, r.height)
                      rectDirty = true
                      forceDraw = true
                  })
                : null
        if (ro) ro.observe(host)
        const io =
            typeof IntersectionObserver !== "undefined"
                ? new IntersectionObserver(
                      (en) => {
                          onScreen = en.some((e) => e.isIntersecting)
                          forceDraw = true
                      },
                      { rootMargin: "128px" }
                  )
                : null
        if (io) io.observe(host)
        const onVisibility = () => {
            pageVisible = document.visibilityState !== "hidden"
            forceDraw = true
        }
        document.addEventListener("visibilitychange", onVisibility)
        const mq = window.matchMedia("(prefers-reduced-motion: reduce)")
        reduceMotion = mq.matches
        const onMQ = (e: MediaQueryListEvent) => {
            reduceMotion = e.matches
            forceDraw = true
        }
        mq.addEventListener("change", onMQ)

        const onLost = (e: Event) => {
            e.preventDefault()
            cancelAnimationFrame(raf)
        }
        const onRestored = () => {
            if (disposed) return
            lastNow = 0
            if (init()) raf = requestAnimationFrame(loop)
            else setFailed(true)
        }
        canvas.addEventListener("webglcontextlost", onLost)
        canvas.addEventListener("webglcontextrestored", onRestored)

        raf = requestAnimationFrame(loop)

        return () => {
            disposed = true
            cancelAnimationFrame(raf)
            host.removeEventListener("pointermove", onRootMove)
            host.removeEventListener("pointerleave", onRootLeave)
            host.removeEventListener("pointerdown", onDown)
            window.removeEventListener("pointermove", onWinMove)
            window.removeEventListener("pointerout", onWinOut)
            window.removeEventListener("pointerup", onUp)
            window.removeEventListener("pointercancel", onUp)
            window.removeEventListener("scroll", onScroll, { capture: true })
            if (ro) ro.disconnect()
            if (io) io.disconnect()
            document.removeEventListener("visibilitychange", onVisibility)
            mq.removeEventListener("change", onMQ)
            canvas.removeEventListener("webglcontextlost", onLost)
            canvas.removeEventListener("webglcontextrestored", onRestored)
            if (gl) {
                if (buffer) gl.deleteBuffer(buffer)
                if (program) gl.deleteProgram(program)
                const lose = gl.getExtension("WEBGL_lose_context")
                if (lose) lose.loseContext()
            }
        }
    }, [])

    // Static stand-in for the rare no-WebGL case.
    const fallback: CSSProperties = failed
        ? {
              width: FIT * scale + "%",
              aspectRatio: "1",
              maxHeight: FIT * scale + "%",
              margin: "auto",
              borderRadius: "50%",
              boxShadow: "inset 0 0 0 3px rgba(255,255,255,0.85), 0 0 12px rgba(255,255,255,0.25)",
              background:
                  "radial-gradient(circle at 50% 50%, " +
                  spriteColor +
                  " 0 58%, transparent 59.5%), linear-gradient(35deg, #e8ecf6 0 38%, rgba(255,255,255,0.06) 52%)",
          }
        : { display: "none" }

    return (
        <div
            ref={hostRef}
            style={{
                position: "relative",
                width: "100%",
                height: "100%",
                overflow: "hidden",
                display: "flex",
                background,
                ...style,
            }}
        >
            <canvas
                ref={canvasRef}
                style={{
                    position: "absolute",
                    inset: 0,
                    width: "100%",
                    height: "100%",
                    display: failed ? "none" : "block",
                }}
            />
            <div style={fallback} />
        </div>
    )
}

/* --------------------------------------------------- property controls */

const A = DEFAULT_ADVANCED

