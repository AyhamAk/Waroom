# /project:snapshot

Explore the current repository and generate a detailed project context snapshot. Follow these steps:

## 1. Repo Structure
- Run `find . -type f | grep -v node_modules | grep -v .git | grep -v dist | grep -v build | head -80` to get the file tree
- Identify the tech stack from package.json / pom.xml / requirements.txt / build files
- Note the top-level architecture (monorepo? frontend+backend split? microservices?)

## 2. Current Work Context
- Check `git status` to see what files are modified/staged
- Check `git log --oneline -10` to see recent commits
- Check `git branch` to identify the current branch and its likely purpose
- If there are any open TODOs or FIXMEs in modified files, surface them

## 3. Key Entry Points
- Find the main entrypoint files (index.ts, main.java, app.py, etc.)
- Find config files (.env.example, application.yml, webpack.config.js, etc.)
- Find test files if any are recently modified

## 4. Active Files (most important)
- Read the top 3–5 recently modified files (from git status or git log) and summarize what each does and what's in progress

## 5. Output
Write the result to `.claude/context-snapshot.md` in this format:

---
# Project Context Snapshot
Generated: {datetime}
Branch: {branch}
---

## Stack
{language, framework, key deps}

## Architecture
{brief 3–5 sentence description}

## Current Branch Purpose
{inferred from branch name + recent commits}

## Modified Files
{list with 1-line description of what's changing in each}

## Active Work Summary
{2–3 paragraph narrative of what is currently being worked on, what's done, and what's next based on TODOs/commits}

## Key Files to Know
{list of 5–10 most important files with paths and roles}
---

After writing the file, print its full contents to stdout.
