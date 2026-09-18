/** FPL club badge art uses the bootstrap `code` (e.g. Arsenal = 3 → t3.png). */

const SHORT_TO_CODE: Record<string, number> = {
  ARS: 3,
  AVL: 7,
  BOU: 91,
  BRE: 94,
  BHA: 36,
  BUR: 90,
  CHE: 8,
  COV: 9,
  CRY: 31,
  EVE: 11,
  FUL: 54,
  HUL: 88,
  IPS: 40,
  LEI: 13,
  LIV: 14,
  LUT: 102,
  MCI: 43,
  MUN: 1,
  NEW: 4,
  NFO: 17,
  SHU: 49,
  SOU: 20,
  SUN: 56,
  TOT: 6,
  WHU: 21,
  WOL: 39,
  LEE: 2,
  LEEDS: 2,
  NOR: 45,
  WAT: 57,
  WBA: 35,
};

const FULL_TO_SHORT: Record<string, string> = {
  arsenal: "ARS",
  "aston villa": "AVL",
  bournemouth: "BOU",
  brentford: "BRE",
  brighton: "BHA",
  "brighton & hove albion": "BHA",
  burnley: "BUR",
  chelsea: "CHE",
  "coventry city": "COV",
  coventry: "COV",
  "crystal palace": "CRY",
  everton: "EVE",
  fulham: "FUL",
  "hull city": "HUL",
  hull: "HUL",
  "ipswich town": "IPS",
  ipswich: "IPS",
  leicester: "LEI",
  liverpool: "LIV",
  luton: "LUT",
  "man city": "MCI",
  "manchester city": "MCI",
  "man utd": "MUN",
  "man united": "MUN",
  "manchester united": "MUN",
  newcastle: "NEW",
  "nottingham forest": "NFO",
  "nott'm forest": "NFO",
  "sheffield united": "SHU",
  "sheffield utd": "SHU",
  southampton: "SOU",
  sunderland: "SUN",
  spurs: "TOT",
  tottenham: "TOT",
  "west ham": "WHU",
  wolves: "WOL",
  leeds: "LEE",
  "leeds united": "LEE",
};

export interface ClubIdentity {
  team?: string | null;
  short_name?: string | null;
  team_name?: string | null;
  team_code?: number | null;
}

export function clubShortName(identity: ClubIdentity): string {
  const candidates = [identity.short_name, identity.team];
  for (const value of candidates) {
    const text = (value ?? "").trim();
    if (!text) {
      continue;
    }
    const upper = text.toUpperCase();
    if (SHORT_TO_CODE[upper]) {
      return upper;
    }
    const mapped = FULL_TO_SHORT[text.toLowerCase()];
    if (mapped) {
      return mapped;
    }
  }
  return (identity.short_name || identity.team || "").trim();
}

export function clubFullName(identity: ClubIdentity): string {
  if (identity.team_name?.trim()) {
    return identity.team_name.trim();
  }
  const raw = (identity.team ?? "").trim();
  if (raw && !SHORT_TO_CODE[raw.toUpperCase()]) {
    return raw;
  }
  return clubShortName(identity);
}

export function clubBadgeCode(teamCode?: number | null, shortName?: string | null): number | null {
  if (teamCode && teamCode > 0) {
    return teamCode;
  }
  if (!shortName) {
    return null;
  }
  return SHORT_TO_CODE[shortName.toUpperCase()] ?? null;
}

export function clubBadgeUrl(teamCode?: number | null, shortName?: string | null): string | null {
  const code = clubBadgeCode(teamCode, shortName);
  if (!code) {
    return null;
  }
  return `https://resources.premierleague.com/premierleague/badges/70/t${code}.png`;
}
