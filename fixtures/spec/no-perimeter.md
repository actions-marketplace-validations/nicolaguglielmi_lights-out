# 9001 — A full meetup keeps a waiting list

- Status: open

## Problem

A meetup at capacity refuses every further signup with a 409.

## Acceptance criteria

Given a meetup at capacity
When a new member signs up
Then they join the waiting list instead of getting a 409

Given a waiting list with one member
When a confirmed attendee cancels
Then the first member on the list becomes an attendee

