import assert from "node:assert/strict";
import { test } from "node:test";
import { minutesUntil, remaining, time, date } from "./format.ts";

test("departure countdown uses the replay timestamp, not the wall clock", () => {
  const replay = "2023-07-13T01:21:00+05:30";
  assert.equal(remaining("2023-07-13T01:55:00+05:30", replay), "34 MIN REMAINING");
  assert.equal(minutesUntil("2023-07-13T02:15:00+05:30", replay), 54);
  assert.equal(minutesUntil("2023-07-13T02:40:00+05:30", replay), 79);
});

test("countdowns handle midnight, expired deadlines, and standby plans", () => {
  assert.equal(minutesUntil("2023-07-13T01:55:00+05:30", "2023-07-12T23:21:00+05:30"), 154);
  assert.equal(remaining("2023-07-13T01:55:00+05:30", "2023-07-13T02:00:00+05:30"), "DEADLINE REACHED");
  assert.equal(remaining(null, "2023-07-13T01:21:00+05:30"), "NO DEPARTURE REQUIRED");
});

test("replay displays in the scenario timezone", () => {
  assert.equal(time("2023-07-12T19:51:00Z", "Asia/Kolkata"), "01:21");
  assert.equal(date("2023-07-12T19:51:00Z", "Asia/Kolkata"), "13 JUL 2023");
});
