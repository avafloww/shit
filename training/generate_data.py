#!/usr/bin/env python3
"""Generate synthetic training data from thefuck rules.

This script creates (command, error_output, correction) triples by:
1. Using a curated set of known command/output scenarios that map to thefuck rules
2. Attempting to invoke thefuck's match() and get_new_command() on each scenario
3. Falling back to the curated correction if the rule can't be invoked dynamically

Output: JSONL with {"command": "...", "stderr": "...", "correction": "..."} per line.
Negative examples (unfixable commands) have expected_correction = None (serialized as "?" in JSONL).
"""

import argparse
import importlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Scenario:
    """A command scenario that a thefuck rule would handle."""

    rule_name: str
    command: str
    output: str
    expected_correction: str | list[str] | None = None
    category: str = "general"


# ---------------------------------------------------------------------------
# GIT SCENARIOS
# ---------------------------------------------------------------------------

GIT_SCENARIOS: list[Scenario] = [
    # --- push errors ---
    Scenario(
        rule_name="git_push",
        command="git push",
        output=(
            "fatal: The current branch feature-login has no upstream branch.\n"
            "To push the current branch and set the remote as upstream, use\n\n"
            "    git push --set-upstream origin feature-login\n"
        ),
        expected_correction="git push --set-upstream origin feature-login",
        category="git",
    ),
    Scenario(
        rule_name="git_push",
        command="git push",
        output=(
            "fatal: The current branch fix-typo has no upstream branch.\n"
            "To push the current branch and set the remote as upstream, use\n\n"
            "    git push --set-upstream origin fix-typo\n"
        ),
        expected_correction="git push --set-upstream origin fix-typo",
        category="git",
    ),
    Scenario(
        rule_name="git_push",
        command="git push",
        output=(
            "fatal: The current branch develop has no upstream branch.\n"
            "To push the current branch and set the remote as upstream, use\n\n"
            "    git push --set-upstream origin develop\n"
        ),
        expected_correction="git push --set-upstream origin develop",
        category="git",
    ),
    Scenario(
        rule_name="git_push_force",
        command="git push",
        output=(
            "To github.com:user/repo.git\n"
            " ! [rejected]        main -> main (non-fast-forward)\n"
            "error: failed to push some refs to 'github.com:user/repo.git'\n"
            "hint: Updates were rejected because the tip of your current branch is behind\n"
        ),
        expected_correction=[
            "git push --force-with-lease",
            "git pull --rebase && git push",
            "git pull && git push",
        ],
        category="git",
    ),
    Scenario(
        rule_name="git_push_force",
        command="git push origin main",
        output=(
            "To github.com:user/repo.git\n"
            " ! [rejected]        main -> main (non-fast-forward)\n"
            "error: failed to push some refs to 'github.com:user/repo.git'\n"
            "hint: Updates were rejected because the tip of your current branch is behind\n"
            "hint: its remote counterpart. Integrate the remote changes (e.g.\n"
            "hint: 'git pull ...') before pushing again.\n"
        ),
        expected_correction=[
            "git push --force-with-lease origin main",
            "git pull --rebase && git push origin main",
            "git pull && git push origin main",
        ],
        category="git",
    ),
    Scenario(
        rule_name="git_push_permission",
        command="git push origin main",
        output=(
            "ERROR: Permission to user/repo.git denied to alice.\n"
            "fatal: Could not read from remote repository.\n"
            "Please make sure you have the correct access rights\n"
            "and the repository exists.\n"
        ),

        category="git",
    ),
    # --- checkout / switch errors ---
    Scenario(
        rule_name="git_checkout",
        command="git checkout mian",
        output=(
            "error: pathspec 'mian' did not match any file(s) known to git\n"
            "hint: 'mian' is similar to 'main'"
        ),
        expected_correction="git checkout main",
        category="git",
    ),
    Scenario(
        rule_name="git_checkout",
        command="git checkout mastre",
        output="error: pathspec 'mastre' did not match any file(s) known to git\n",
        expected_correction="git checkout master",
        category="git",
    ),
    Scenario(
        rule_name="git_checkout",
        command="git checkout develpo",
        output=(
            "error: pathspec 'develpo' did not match any file(s) known to git\n"
            "hint: 'develpo' is similar to 'develop'"
        ),
        expected_correction="git checkout develop",
        category="git",
    ),
    Scenario(
        rule_name="git_checkout_file",
        command="git checkout src/main.rs",
        output="error: pathspec 'src/main.rs' did not match any file(s) known to git\n",
        expected_correction="git checkout -- src/main.rs",
        category="git",
    ),
    Scenario(
        rule_name="git_checkout_uncommitted",
        command="git checkout feature-api",
        output=(
            "error: Your local changes to the following files would be overwritten by checkout:\n"
            "\tsrc/app.py\n"
            "Please commit your changes or stash them before you switch branches.\n"
            "Aborting\n"
        ),
        expected_correction=[
            "git stash && git checkout feature-api",
            "git checkout -f feature-api",
        ],
        category="git",
    ),
    Scenario(
        rule_name="git_switch",
        command="git switch mian",
        output=(
            "fatal: invalid reference: mian\n"
            "hint: 'mian' is similar to 'main'"
        ),
        expected_correction="git switch main",
        category="git",
    ),
    Scenario(
        rule_name="git_branch_exists",
        command="git checkout -b feature-login",
        output="fatal: a branch named 'feature-login' already exists\n",
        expected_correction="git checkout feature-login",
        category="git",
    ),
    Scenario(
        rule_name="git_branch_exists",
        command="git checkout -b main",
        output="fatal: a branch named 'main' already exists\n",
        expected_correction="git checkout main",
        category="git",
    ),
    Scenario(
        rule_name="git_branch_delete",
        command="git branch -d feature-old",
        output=(
            "error: The branch 'feature-old' is not fully merged.\n"
            "If you are sure you want to delete it, run 'git branch -D feature-old'.\n"
        ),
        expected_correction="git branch -D feature-old",
        category="git",
    ),
    Scenario(
        rule_name="git_branch_delete",
        command="git branch -d feature-wip",
        output=(
            "error: The branch 'feature-wip' is not fully merged.\n"
            "If you are sure you want to delete it, run 'git branch -D feature-wip'.\n"
        ),
        expected_correction="git branch -D feature-wip",
        category="git",
    ),
    Scenario(
        rule_name="git_branch_not_found",
        command="git branch -d nonexistent-branch",
        output="error: branch 'nonexistent-branch' not found.\n",

        category="git",
    ),
    # --- commit errors ---
    Scenario(
        rule_name="git_commit_amend",
        command="git commit",
        output="On branch main\nnothing to commit, working tree clean\n",
        expected_correction="git commit --allow-empty",
        category="git",
    ),
    Scenario(
        rule_name="git_commit_nothing",
        command="git commit -m 'fix bug'",
        output=(
            "On branch main\n"
            "nothing to commit, working tree clean\n"
        ),
        expected_correction="git commit --allow-empty -m 'fix bug'",
        category="git",
    ),
    Scenario(
        rule_name="git_commit_untracked",
        command="git commit -m 'add feature'",
        output=(
            "On branch feature-api\n"
            "Untracked files:\n"
            "\tsrc/new_file.py\n"
            "\n"
            "nothing added to commit but untracked files present (use 'git add' to track)\n"
        ),
        expected_correction="git add . && git commit -m 'add feature'",
        category="git",
    ),
    Scenario(
        rule_name="git_commit_empty_message",
        command="git commit -m ''",
        output="error: switch `m' requires a value\n",
        expected_correction="git commit",
        category="git",
    ),
    # --- add errors ---
    Scenario(
        rule_name="git_add",
        command="git add .",
        output=(
            "The following paths are ignored by one of your .gitignore files:\n"
            "node_modules\n"
            "hint: Use -f if you really want to add them.\n"
        ),
        expected_correction="git add . -f",
        category="git",
    ),
    Scenario(
        rule_name="git_add",
        command="git add dist/",
        output=(
            "The following paths are ignored by one of your .gitignore files:\n"
            "dist/\n"
            "hint: Use -f if you really want to add them.\n"
        ),
        expected_correction="git add dist/ -f",
        category="git",
    ),
    # --- stash errors ---
    Scenario(
        rule_name="git_stash",
        command="git stash get",
        output=(
            "git: 'stash get' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\tstash pop"
        ),
        expected_correction="git stash pop",
        category="git",
    ),
    Scenario(
        rule_name="git_stash_empty",
        command="git stash pop",
        output="error: No stash entries found.\n",

        category="git",
    ),
    Scenario(
        rule_name="git_stash_conflict",
        command="git stash apply",
        output=(
            "Auto-merging src/main.rs\n"
            "CONFLICT (content): Merge conflict in src/main.rs\n"
            "The stash entry is kept in case you need it again.\n"
        ),
        expected_correction="git checkout -- src/main.rs && git stash apply",
        category="git",
    ),
    # --- pull errors ---
    Scenario(
        rule_name="git_pull",
        command="git pull",
        output=(
            "There is no tracking information for the current branch.\n"
            "Please specify which branch you want to merge with.\n"
            "    git pull <remote> <branch>\n\n"
            "If you wish to set tracking information for this branch you can do so with:\n\n"
            "    git branch --set-upstream-to=origin/<branch> feature-x\n"
        ),
        expected_correction="git pull origin feature-x",
        category="git",
    ),
    Scenario(
        rule_name="git_pull_uncommitted",
        command="git pull",
        output=(
            "error: Your local changes to the following files would be overwritten by merge:\n"
            "\tsrc/main.rs\n"
            "Please commit your changes or stash them before you merge.\n"
        ),
        expected_correction="git stash && git pull && git stash pop",
        category="git",
    ),
    Scenario(
        rule_name="git_pull_diverged",
        command="git pull",
        output=(
            "hint: You have divergent branches and need to specify how to reconcile them.\n"
            "hint: You can do so by running one of the following commands sometime before\n"
            "hint: your next pull:\n"
            "hint:\n"
            "hint:   git config pull.rebase false  # merge\n"
            "hint:   git config pull.rebase true   # rebase\n"
            "hint:   git config pull.ff only       # fast-forward only\n"
            "fatal: Need to specify how to reconcile divergent branches.\n"
        ),
        expected_correction="git pull --rebase",
        category="git",
    ),
    # --- merge errors ---
    Scenario(
        rule_name="git_merge",
        command="git merge feature",
        output=(
            "merge: feature - not something we can merge\n\n"
            "Did you mean this?\n\tfeature-login\n"
        ),
        expected_correction="git merge feature-login",
        category="git",
    ),
    Scenario(
        rule_name="git_merge_conflict",
        command="git merge feature-api",
        output=(
            "Auto-merging src/app.py\n"
            "CONFLICT (content): Merge conflict in src/app.py\n"
            "Automatic merge failed; fix conflicts and then commit the result.\n"
        ),
        expected_correction=[
            "git merge --abort",
            "git mergetool",
        ],
        category="git",
    ),
    Scenario(
        rule_name="git_merge_already",
        command="git merge feature-done",
        output="Already up to date.\n",

        category="git",
    ),
    # --- rebase errors ---
    Scenario(
        rule_name="git_rebase",
        command="git rebase main",
        output=(
            "CONFLICT (content): Merge conflict in src/app.py\n"
            "error: could not apply abc1234... add feature\n"
            "hint: Resolve all conflicts manually, mark them as resolved with\n"
            "hint: 'git add/rm <conflicted_files>', then run 'git rebase --continue'.\n"
        ),
        expected_correction=[
            "git rebase --abort",
            "git rebase --skip",
        ],
        category="git",
    ),
    Scenario(
        rule_name="git_rebase_already",
        command="git rebase origin/main",
        output="Current branch main is up to date.\n",

        category="git",
    ),
    # --- remote errors ---
    Scenario(
        rule_name="git_remote_exists",
        command="git remote add origin git@github.com:user/repo.git",
        output="error: remote origin already exists.\n",
        expected_correction="git remote set-url origin git@github.com:user/repo.git",
        category="git",
    ),
    Scenario(
        rule_name="git_remote_not_found",
        command="git remote remove upstream",
        output="fatal: No such remote: 'upstream'\n",

        category="git",
    ),
    # --- clone errors ---
    Scenario(
        rule_name="git_clone_not_found",
        command="git clone git@github.com:user/nonexistent.git",
        output=(
            "ERROR: Repository not found.\n"
            "fatal: Could not read from remote repository.\n"
            "Please make sure you have the correct access rights\n"
            "and the repository exists.\n"
        ),

        category="git",
    ),
    Scenario(
        rule_name="git_clone_exists",
        command="git clone git@github.com:user/myrepo.git",
        output="fatal: destination path 'myrepo' already exists and is not an empty directory.\n",
        expected_correction="git clone git@github.com:user/myrepo.git myrepo-2",
        category="git",
    ),
    # --- tag errors ---
    Scenario(
        rule_name="git_tag_exists",
        command="git tag v1.0.0",
        output="fatal: tag 'v1.0.0' already exists\n",
        expected_correction="git tag -f v1.0.0",
        category="git",
    ),
    Scenario(
        rule_name="git_tag_exists",
        command="git tag v2.3.1",
        output="fatal: tag 'v2.3.1' already exists\n",
        expected_correction="git tag -f v2.3.1",
        category="git",
    ),
    # --- cherry-pick errors ---
    Scenario(
        rule_name="git_cherry_pick",
        command="git cherry-pick abc1234",
        output=(
            "error: could not apply abc1234... fix memory leak\n"
            "hint: After resolving the conflicts, mark them with\n"
            "hint: 'git add <paths>' or 'git rm <paths>'\n"
            "hint: and commit the result with 'git commit'\n"
        ),
        expected_correction="git cherry-pick --abort",
        category="git",
    ),
    # --- diff errors ---
    Scenario(
        rule_name="git_diff_staged",
        command="git diff",
        output="",
        expected_correction="git diff --staged",
        category="git",
    ),
    Scenario(
        rule_name="git_diff_branch",
        command="git diff mian",
        output="fatal: ambiguous argument 'mian': unknown revision or path not in the working tree.\n",
        expected_correction="git diff main",
        category="git",
    ),
    # --- log errors ---
    Scenario(
        rule_name="git_log_graph",
        command="git log --oneline --grpah",
        output="error: unknown switch `g'\n",
        expected_correction="git log --oneline --graph",
        category="git",
    ),
    # --- typo in git command ---
    Scenario(
        rule_name="git_typo_psuh",
        command="git psuh",
        output=(
            "git: 'psuh' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\tpush\n"
        ),
        expected_correction="git push",
        category="git",
    ),
    Scenario(
        rule_name="git_typo_comit",
        command="git comit",
        output=(
            "git: 'comit' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\tcommit\n"
        ),
        expected_correction="git commit",
        category="git",
    ),
    Scenario(
        rule_name="git_typo_stauts",
        command="git stauts",
        output=(
            "git: 'stauts' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\tstatus\n"
        ),
        expected_correction="git status",
        category="git",
    ),
    Scenario(
        rule_name="git_typo_staus",
        command="git staus",
        output=(
            "git: 'staus' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\tstatus\n"
        ),
        expected_correction="git status",
        category="git",
    ),
    Scenario(
        rule_name="git_typo_chekcout",
        command="git chekcout main",
        output=(
            "git: 'chekcout' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\tcheckout\n"
        ),
        expected_correction="git checkout main",
        category="git",
    ),
    Scenario(
        rule_name="git_typo_merg",
        command="git merg feature-login",
        output=(
            "git: 'merg' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\tmerge\n"
        ),
        expected_correction="git merge feature-login",
        category="git",
    ),
    Scenario(
        rule_name="git_typo_plul",
        command="git plul",
        output=(
            "git: 'plul' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\tpull\n"
        ),
        expected_correction="git pull",
        category="git",
    ),
    Scenario(
        rule_name="git_typo_dif",
        command="git dif",
        output=(
            "git: 'dif' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\tdiff\n"
        ),
        expected_correction="git diff",
        category="git",
    ),
    Scenario(
        rule_name="git_typo_fetc",
        command="git fetc",
        output=(
            "git: 'fetc' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\tfetch\n"
        ),
        expected_correction="git fetch",
        category="git",
    ),
    Scenario(
        rule_name="git_typo_lgo",
        command="git lgo",
        output=(
            "git: 'lgo' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\tlog\n"
        ),
        expected_correction="git log",
        category="git",
    ),
    Scenario(
        rule_name="git_typo_reabse",
        command="git reabse main",
        output=(
            "git: 'reabse' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\trebase\n"
        ),
        expected_correction="git rebase main",
        category="git",
    ),
    Scenario(
        rule_name="git_typo_clon",
        command="git clon git@github.com:user/repo.git",
        output=(
            "git: 'clon' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\tclone\n"
        ),
        expected_correction="git clone git@github.com:user/repo.git",
        category="git",
    ),
    Scenario(
        rule_name="git_typo_intit",
        command="git intit",
        output=(
            "git: 'intit' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\tinit\n"
        ),
        expected_correction="git init",
        category="git",
    ),
    Scenario(
        rule_name="git_typo_rset",
        command="git rset HEAD~1",
        output=(
            "git: 'rset' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\treset\n"
        ),
        expected_correction="git reset HEAD~1",
        category="git",
    ),
    Scenario(
        rule_name="git_typo_shwo",
        command="git shwo",
        output=(
            "git: 'shwo' is not a git command. See 'git --help'.\n\n"
            "The most similar command is\n\tshow\n"
        ),
        expected_correction="git show",
        category="git",
    ),
    # --- multi-alternative: push diverged ---
    Scenario(
        rule_name="git_push_diverged",
        command="git push origin feature-login",
        output=(
            "To github.com:user/repo.git\n"
            " ! [rejected]        feature-login -> feature-login (non-fast-forward)\n"
            "error: failed to push some refs to 'github.com:user/repo.git'\n"
            "hint: Updates were rejected because the tip of your current branch is behind\n"
            "hint: its remote counterpart. If you want to integrate the remote changes,\n"
            "hint: use 'git pull' before pushing again.\n"
        ),
        expected_correction=[
            "git push --force-with-lease origin feature-login",
            "git pull --rebase && git push origin feature-login",
        ],
        category="git",
    ),
    # --- multi-alternative: cherry-pick conflict ---
    Scenario(
        rule_name="git_cherry_pick_conflict",
        command="git cherry-pick abc1234",
        output=(
            "error: could not apply abc1234... some commit\n"
            "hint: After resolving the conflicts, mark the corrected paths\n"
            "hint: with 'git add <paths>' or 'git rm <paths>'\n"
            "hint: and commit the result with 'git commit'\n"
        ),
        expected_correction=[
            "git cherry-pick --abort",
            "git cherry-pick --skip",
        ],
        category="git",
    ),
    # --- multi-alternative: git reset ambiguous ---
    Scenario(
        rule_name="git_reset_ambiguous",
        command="git reset src/app.py",
        output=(
            "Unstaged changes after reset:\n"
            "M\tsrc/app.py\n"
        ),
        expected_correction=[
            "git reset HEAD src/app.py",
            "git checkout -- src/app.py",
        ],
        category="git",
    ),
    # --- multi-alternative: stash conflict on pop ---
    Scenario(
        rule_name="git_stash_pop_conflict",
        command="git stash pop",
        output=(
            "Auto-merging src/app.py\n"
            "CONFLICT (content): Merge conflict in src/app.py\n"
            "The stash entry is kept in case you need it again.\n"
        ),
        expected_correction=[
            "git checkout --theirs src/app.py && git add src/app.py",
            "git checkout --ours src/app.py && git add src/app.py",
            "git stash drop",
        ],
        category="git",
    ),
    # --- multi-alternative: git pull conflict ---
    Scenario(
        rule_name="git_pull_conflict",
        command="git pull",
        output=(
            "Auto-merging src/main.rs\n"
            "CONFLICT (content): Merge conflict in src/main.rs\n"
            "Automatic merge failed; fix conflicts and then commit the result.\n"
        ),
        expected_correction=[
            "git merge --abort",
            "git mergetool",
        ],
        category="git",
    ),
    # --- multi-alternative: git pull with uncommitted changes ---
    Scenario(
        rule_name="git_pull_dirty",
        command="git pull",
        output=(
            "error: Your local changes to the following files would be overwritten by merge:\n"
            "\tsrc/app.py\n"
            "Please commit your changes or stash them before you merge.\n"
            "Aborting\n"
        ),
        expected_correction=[
            "git stash && git pull",
            "git commit -am 'wip' && git pull",
        ],
        category="git",
    ),
    # --- multi-alternative: switch with uncommitted changes ---
    Scenario(
        rule_name="git_switch_uncommitted",
        command="git switch main",
        output=(
            "error: Your local changes to the following files would be overwritten by checkout:\n"
            "\tsrc/app.py\n"
            "Please commit your changes or stash them before you switch branches.\n"
            "Aborting\n"
        ),
        expected_correction=[
            "git stash && git switch main",
            "git switch -f main",
        ],
        category="git",
    ),
]

# ---------------------------------------------------------------------------
# PACKAGE MANAGER SCENARIOS
# ---------------------------------------------------------------------------

PACKAGE_MANAGER_SCENARIOS: list[Scenario] = [
    # --- pip ---
    Scenario(
        rule_name="pip_unknown_command",
        command="pip isntall requests",
        output='ERROR: unknown command "isntall" - maybe you meant "install"\n',
        expected_correction="pip install requests",
        category="package_manager",
    ),
    Scenario(
        rule_name="pip_unknown_command",
        command="pip instal flask",
        output='ERROR: unknown command "instal" - maybe you meant "install"\n',
        expected_correction="pip install flask",
        category="package_manager",
    ),
    Scenario(
        rule_name="pip_unknown_command",
        command="pip intall numpy",
        output='ERROR: unknown command "intall" - maybe you meant "install"\n',
        expected_correction="pip install numpy",
        category="package_manager",
    ),
    Scenario(
        rule_name="pip_not_found",
        command="pip install nonexistent-package-xyz",
        output=(
            "ERROR: Could not find a version that satisfies the requirement nonexistent-package-xyz\n"
            "ERROR: No matching distribution found for nonexistent-package-xyz\n"
        ),

        category="package_manager",
    ),
    Scenario(
        rule_name="pip_permission",
        command="pip install requests",
        output=(
            "ERROR: Could not install packages due to an OSError: [Errno 13] Permission denied: "
            "'/usr/lib/python3/dist-packages/requests'\n"
            "Consider using the `--user` switch or an existing virtual environment.\n"
        ),
        expected_correction=[
            "pip install --user requests",
            "sudo pip install requests",
        ],
        category="package_manager",
    ),
    Scenario(
        rule_name="pip_version_conflict",
        command="pip install django==5.0.0",
        output=(
            "ERROR: Cannot install django==5.0.0 because these package versions have conflicting dependencies.\n"
            "The conflict is caused by:\n"
            "    The user requested django==5.0.0\n"
            "    djangorestframework 3.14.0 depends on django>=3.0\n"
        ),
        expected_correction="pip install django",
        category="package_manager",
    ),
    Scenario(
        rule_name="pip3_not_found",
        command="pip3 install requests",
        output="bash: pip3: command not found\n",
        expected_correction="pip install requests",
        category="package_manager",
    ),
    Scenario(
        rule_name="python_module_error",
        command="python app.py",
        output="ModuleNotFoundError: No module named 'flask'\n",
        expected_correction="pip install flask && python app.py",
        category="package_manager",
    ),
    Scenario(
        rule_name="python_module_error",
        command="python server.py",
        output="ModuleNotFoundError: No module named 'fastapi'\n",
        expected_correction="pip install fastapi && python server.py",
        category="package_manager",
    ),
    Scenario(
        rule_name="python_module_error",
        command="python train.py",
        output="ModuleNotFoundError: No module named 'numpy'\n",
        expected_correction="pip install numpy && python train.py",
        category="package_manager",
    ),
    Scenario(
        rule_name="python_module_error",
        command="python script.py",
        output="ModuleNotFoundError: No module named 'requests'\n",
        expected_correction="pip install requests && python script.py",
        category="package_manager",
    ),
    Scenario(
        rule_name="python_module_error",
        command="python manage.py runserver",
        output="ModuleNotFoundError: No module named 'django'\n",
        expected_correction="pip install django && python manage.py runserver",
        category="package_manager",
    ),
    Scenario(
        rule_name="python_module_error",
        command="python scraper.py",
        output="ModuleNotFoundError: No module named 'bs4'\n",
        expected_correction="pip install beautifulsoup4 && python scraper.py",
        category="package_manager",
    ),
    Scenario(
        rule_name="python_module_error",
        command="python analyze.py",
        output="ModuleNotFoundError: No module named 'pandas'\n",
        expected_correction="pip install pandas && python analyze.py",
        category="package_manager",
    ),
    # --- npm ---
    Scenario(
        rule_name="npm_wrong_command",
        command="npm run biuld",
        output=(
            'npm error Missing script: "biuld"\n\n'
            "npm error To see a list of scripts, run:\n"
            "npm error   npm run\n\n"
            'npm error Did you mean this?\n  npm run build\n'
        ),
        expected_correction="npm run build",
        category="package_manager",
    ),
    Scenario(
        rule_name="npm_wrong_command",
        command="npm run statr",
        output=(
            'npm error Missing script: "statr"\n\n'
            "npm error To see a list of scripts, run:\n"
            "npm error   npm run\n\n"
            'npm error Did you mean this?\n  npm run start\n'
        ),
        expected_correction="npm run start",
        category="package_manager",
    ),
    Scenario(
        rule_name="npm_wrong_command",
        command="npm run tset",
        output=(
            'npm error Missing script: "tset"\n\n'
            "npm error To see a list of scripts, run:\n"
            "npm error   npm run\n\n"
            'npm error Did you mean this?\n  npm run test\n'
        ),
        expected_correction="npm run test",
        category="package_manager",
    ),
    Scenario(
        rule_name="npm_package_not_found",
        command="npm install nonexistent-pkg-xyz",
        output=(
            "npm error code E404\n"
            "npm error 404 Not Found - GET https://registry.npmjs.org/nonexistent-pkg-xyz\n"
            "npm error 404 'nonexistent-pkg-xyz@latest' is not in this registry.\n"
        ),

        category="package_manager",
    ),
    Scenario(
        rule_name="npm_permission",
        command="npm install -g typescript",
        output=(
            "npm error code EACCES\n"
            "npm error syscall mkdir\n"
            "npm error path /usr/local/lib/node_modules\n"
            "npm error errno -13\n"
            "npm error Error: EACCES: permission denied, mkdir '/usr/local/lib/node_modules'\n"
        ),
        expected_correction=[
            "sudo npm install -g typescript",
            "npm install -g typescript --prefix ~/.local",
        ],
        category="package_manager",
    ),
    Scenario(
        rule_name="npm_peer_dep",
        command="npm install react-router-dom",
        output=(
            "npm warn ERESOLVE overriding peer dependency\n"
            "npm warn Found: react@17.0.2\n"
            "npm warn node_modules/react\n"
            "npm warn   react@'17.0.2' from the root project\n"
            "npm warn Could not resolve dependency:\n"
            "npm warn peer react@'>=18.0.0' from react-router-dom@6.21.0\n"
        ),
        expected_correction="npm install react-router-dom --legacy-peer-deps",
        category="package_manager",
    ),
    Scenario(
        rule_name="npm_no_such_file",
        command="npm start",
        output=(
            "npm error Missing script: 'start'\n"
            "npm error\n"
            "npm error Did you mean one of these?\n"
            "npm error   npm run dev\n"
        ),
        expected_correction="npm run dev",
        category="package_manager",
    ),
    # --- yarn ---
    Scenario(
        rule_name="yarn_not_found",
        command="yarn add nonexistent-package-xyz",
        output=(
            "error An unexpected error occurred: \"https://registry.yarnpkg.com/nonexistent-package-xyz: Not found\"\n"
        ),

        category="package_manager",
    ),
    Scenario(
        rule_name="yarn_wrong_command",
        command="yarn biuld",
        output=(
            "error Command 'biuld' not found.\n"
            "info Visit https://yarnpkg.com/en/docs/cli/ for documentation about this command.\n"
        ),
        expected_correction="yarn build",
        category="package_manager",
    ),
    Scenario(
        rule_name="yarn_missing_script",
        command="yarn run deploy",
        output=(
            "error Command 'deploy' not found.\n"
            "info Visit https://yarnpkg.com/en/docs/cli/run for documentation about this command.\n"
        ),

        category="package_manager",
    ),
    # --- cargo ---
    Scenario(
        rule_name="cargo_no_command",
        command="cargo biuld",
        output=(
            "error: no such command: `biuld`\n\n"
            "\tDid you mean `build`?\n"
        ),
        expected_correction="cargo build",
        category="package_manager",
    ),
    Scenario(
        rule_name="cargo_no_command",
        command="cargo tset",
        output=(
            "error: no such command: `tset`\n\n"
            "\tDid you mean `test`?\n"
        ),
        expected_correction="cargo test",
        category="package_manager",
    ),
    Scenario(
        rule_name="cargo_not_found",
        command="cargo install nonexistent-crate-xyz",
        output=(
            "error: could not find crate `nonexistent-crate-xyz` on crates.io\n"
        ),

        category="package_manager",
    ),
    Scenario(
        rule_name="cargo_feature",
        command="cargo build --features nonexistent-feature",
        output=(
            "error[E0635]: unknown feature `nonexistent-feature`\n"
            "  --> Cargo.toml:5:1\n"
        ),

        category="package_manager",
    ),
    # --- apt/apt-get ---
    Scenario(
        rule_name="apt_get_search",
        command="apt-get search vim",
        output="E: Invalid operation search\n",
        expected_correction="apt-cache search vim",
        category="package_manager",
    ),
    Scenario(
        rule_name="apt_package_not_found",
        command="apt install nonexistent-package-xyz",
        output=(
            "Reading package lists... Done\n"
            "Building dependency tree... Done\n"
            "E: Unable to locate package nonexistent-package-xyz\n"
        ),
        expected_correction="apt-cache search nonexistent-package-xyz",
        category="package_manager",
    ),
    Scenario(
        rule_name="apt_permission",
        command="apt install curl",
        output="E: Could not open lock file /var/lib/dpkg/lock-frontend - open (13: Permission denied)\n"
               "E: Unable to acquire the dpkg frontend lock, are you root?\n",
        expected_correction="sudo apt install curl",
        category="package_manager",
    ),
    Scenario(
        rule_name="apt_locked",
        command="apt-get install git",
        output=(
            "E: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process 1234\n"
            "E: Unable to acquire the dpkg frontend lock, are you root?\n"
        ),
        expected_correction="sudo killall apt apt-get && sudo apt-get install git",
        category="package_manager",
    ),
    Scenario(
        rule_name="apt_unmet_deps",
        command="apt-get install mypackage",
        output=(
            "Reading package lists... Done\n"
            "Building dependency tree\n"
            "The following packages have unmet dependencies:\n"
            " mypackage : Depends: libssl1.0 but it is not installable\n"
            "E: Unable to correct problems, you have held broken packages.\n"
        ),
        expected_correction="sudo apt-get install -f",
        category="package_manager",
    ),
    # --- pacman ---
    Scenario(
        rule_name="pacman_not_found",
        command="pacman -S nonexistent-pkg",
        output="error: target not found: nonexistent-pkg\n",
        expected_correction="yay -S nonexistent-pkg",
        category="package_manager",
    ),
    Scenario(
        rule_name="pacman_conflict",
        command="pacman -S python",
        output=(
            "resolving dependencies...\n"
            "looking for conflicting packages...\n"
            ":: python and python2 are in conflict. Remove python2? [y/N]\n"
        ),
        expected_correction="sudo pacman -S python --ask",
        category="package_manager",
    ),
    Scenario(
        rule_name="pacman_permission",
        command="pacman -Syu",
        output="error: you cannot perform this operation unless you are root.\n",
        expected_correction="sudo pacman -Syu",
        category="package_manager",
    ),
    # --- brew ---
    Scenario(
        rule_name="brew_not_found",
        command="brew install nonexistent-formula",
        output=(
            "Error: No available formula with the name \"nonexistent-formula\".\n"
        ),
        expected_correction="brew search nonexistent-formula",
        category="package_manager",
    ),
    Scenario(
        rule_name="brew_already_installed",
        command="brew install git",
        output=(
            "Warning: git 2.42.0 is already installed and up-to-date.\n"
            "To reinstall 2.42.0, run:\n"
            "  brew reinstall git\n"
        ),
        expected_correction="brew reinstall git",
        category="package_manager",
    ),
    Scenario(
        rule_name="brew_cask_not_found",
        command="brew install --cask nonexistent-app",
        output=(
            "Error: Cask 'nonexistent-app' is unavailable: No Cask with this name exists!\n"
        ),
        expected_correction="brew search --cask nonexistent-app",
        category="package_manager",
    ),
]

# ---------------------------------------------------------------------------
# FILE / DIRECTORY OPERATION SCENARIOS
# ---------------------------------------------------------------------------

FILE_SCENARIOS: list[Scenario] = [
    # --- rm ---
    Scenario(
        rule_name="rm_dir",
        command="rm mydir",
        output="rm: cannot remove 'mydir': Is a directory\n",
        expected_correction="rm -rf mydir",
        category="file_ops",
    ),
    Scenario(
        rule_name="rm_dir",
        command="rm src/",
        output="rm: cannot remove 'src/': Is a directory\n",
        expected_correction="rm -rf src/",
        category="file_ops",
    ),
    Scenario(
        rule_name="rm_dir",
        command="rm -r mydir",
        output="rm: cannot remove 'mydir': Permission denied\n",
        expected_correction="sudo rm -rf mydir",
        category="file_ops",
    ),
    Scenario(
        rule_name="rm_no_file",
        command="rm nonexistent.txt",
        output="rm: cannot remove 'nonexistent.txt': No such file or directory\n",

        category="file_ops",
    ),
    # --- cp ---
    Scenario(
        rule_name="cp_omit_dir",
        command="cp src/ dest/",
        output="cp: -r not specified; omitting directory 'src/'\n",
        expected_correction="cp -r src/ dest/",
        category="file_ops",
    ),
    Scenario(
        rule_name="cp_omit_dir",
        command="cp myproject/ backup/",
        output="cp: -r not specified; omitting directory 'myproject/'\n",
        expected_correction="cp -r myproject/ backup/",
        category="file_ops",
    ),
    Scenario(
        rule_name="cp_permission",
        command="cp file.txt /etc/file.txt",
        output="cp: cannot create regular file '/etc/file.txt': Permission denied\n",
        expected_correction="sudo cp file.txt /etc/file.txt",
        category="file_ops",
    ),
    Scenario(
        rule_name="cp_no_file",
        command="cp nonexistent.txt dest.txt",
        output="cp: cannot stat 'nonexistent.txt': No such file or directory\n",

        category="file_ops",
    ),
    # --- mv ---
    Scenario(
        rule_name="mv_permission",
        command="mv myfile.txt /etc/myfile.txt",
        output="mv: cannot move 'myfile.txt' to '/etc/myfile.txt': Permission denied\n",
        expected_correction="sudo mv myfile.txt /etc/myfile.txt",
        category="file_ops",
    ),
    Scenario(
        rule_name="mv_cross_device",
        command="mv /tmp/bigfile.tar.gz /mnt/storage/",
        output="mv: cannot move '/tmp/bigfile.tar.gz' to '/mnt/storage/bigfile.tar.gz': Invalid cross-device link\n",
        expected_correction="cp /tmp/bigfile.tar.gz /mnt/storage/ && rm /tmp/bigfile.tar.gz",
        category="file_ops",
    ),
    Scenario(
        rule_name="mv_no_file",
        command="mv nonexistent.txt newname.txt",
        output="mv: cannot stat 'nonexistent.txt': No such file or directory\n",

        category="file_ops",
    ),
    # --- mkdir ---
    Scenario(
        rule_name="mkdir_exists",
        command="mkdir mydir",
        output="mkdir: cannot create directory 'mydir': File exists\n",

        category="file_ops",
    ),
    Scenario(
        rule_name="mkdir_permission",
        command="mkdir /opt/myapp",
        output="mkdir: cannot create directory '/opt/myapp': Permission denied\n",
        expected_correction="sudo mkdir /opt/myapp",
        category="file_ops",
    ),
    Scenario(
        rule_name="mkdir_parent_missing",
        command="mkdir a/b/c",
        output="mkdir: cannot create directory 'a/b/c': No such file or directory\n",
        expected_correction="mkdir -p a/b/c",
        category="file_ops",
    ),
    Scenario(
        rule_name="mkdir_parent_missing",
        command="mkdir projects/new-app/src",
        output="mkdir: cannot create directory 'projects/new-app/src': No such file or directory\n",
        expected_correction="mkdir -p projects/new-app/src",
        category="file_ops",
    ),
    # --- chmod / chown ---
    Scenario(
        rule_name="chmod_permission",
        command="chmod 755 /etc/passwd",
        output="chmod: changing permissions of '/etc/passwd': Operation not permitted\n",
        expected_correction="sudo chmod 755 /etc/passwd",
        category="file_ops",
    ),
    Scenario(
        rule_name="chmod_invalid_mode",
        command="chmod 999 myfile.txt",
        output="chmod: invalid mode: '999'\n",
        expected_correction="chmod 755 myfile.txt",
        category="file_ops",
    ),
    Scenario(
        rule_name="chown_permission",
        command="chown root:root myfile.txt",
        output="chown: changing ownership of 'myfile.txt': Operation not permitted\n",
        expected_correction="sudo chown root:root myfile.txt",
        category="file_ops",
    ),
    # --- cat ---
    Scenario(
        rule_name="cat_dir",
        command="cat src/",
        output="cat: src/: Is a directory\n",
        expected_correction="ls src/",
        category="file_ops",
    ),
    Scenario(
        rule_name="cat_dir",
        command="cat myproject/",
        output="cat: myproject/: Is a directory\n",
        expected_correction="ls myproject/",
        category="file_ops",
    ),
    Scenario(
        rule_name="cat_permission",
        command="cat /var/log/syslog",
        output="cat: /var/log/syslog: Permission denied\n",
        expected_correction="sudo cat /var/log/syslog",
        category="file_ops",
    ),
    Scenario(
        rule_name="cat_no_file",
        command="cat nonexistent.txt",
        output="cat: nonexistent.txt: No such file or directory\n",

        category="file_ops",
    ),
    # --- ln ---
    Scenario(
        rule_name="ln_exists",
        command="ln -s /usr/local/bin/python3 /usr/bin/python",
        output="ln: failed to create symbolic link '/usr/bin/python': File exists\n",
        expected_correction="ln -sf /usr/local/bin/python3 /usr/bin/python",
        category="file_ops",
    ),
    Scenario(
        rule_name="ln_no_src",
        command="ln -s nonexistent.txt link.txt",
        output="ln: failed to create symbolic link 'link.txt': No such file or directory\n",

        category="file_ops",
    ),
    # --- cd ---
    Scenario(
        rule_name="cd_mkdir",
        command="cd projects/new-app",
        output="bash: cd: projects/new-app: No such file or directory\n",
        expected_correction="mkdir -p projects/new-app && cd projects/new-app",
        category="file_ops",
    ),
    Scenario(
        rule_name="cd_mkdir",
        command="cd workspace/experiment",
        output="bash: cd: workspace/experiment: No such file or directory\n",
        expected_correction="mkdir -p workspace/experiment && cd workspace/experiment",
        category="file_ops",
    ),
    Scenario(
        rule_name="cd_not_dir",
        command="cd myfile.txt",
        output="bash: cd: myfile.txt: Not a directory\n",

        category="file_ops",
    ),
]

# ---------------------------------------------------------------------------
# COMMAND NOT FOUND SCENARIOS
# ---------------------------------------------------------------------------

COMMAND_NOT_FOUND_SCENARIOS: list[Scenario] = [
    Scenario(
        rule_name="python_not_found",
        command="python3 script.py",
        output="bash: python3: command not found\n",
        expected_correction="python script.py",
        category="command_not_found",
    ),
    Scenario(
        rule_name="python_not_found",
        command="python3 manage.py runserver",
        output="bash: python3: command not found\n",
        expected_correction="python manage.py runserver",
        category="command_not_found",
    ),
    Scenario(
        rule_name="python_not_found",
        command="python3 -m pip install requests",
        output="bash: python3: command not found\n",
        expected_correction="python -m pip install requests",
        category="command_not_found",
    ),
    Scenario(
        rule_name="sl_ls",
        command="sl",
        output="bash: sl: command not found\n",
        expected_correction="ls",
        category="command_not_found",
    ),
    Scenario(
        rule_name="gti_git",
        command="gti status",
        output="bash: gti: command not found\n",
        expected_correction="git status",
        category="command_not_found",
    ),
    Scenario(
        rule_name="gti_git",
        command="gti commit -m 'fix bug'",
        output="bash: gti: command not found\n",
        expected_correction="git commit -m 'fix bug'",
        category="command_not_found",
    ),
    Scenario(
        rule_name="gti_git",
        command="gti push",
        output="bash: gti: command not found\n",
        expected_correction="git push",
        category="command_not_found",
    ),
    Scenario(
        rule_name="pytohn_python",
        command="pytohn script.py",
        output="bash: pytohn: command not found\n",
        expected_correction="python script.py",
        category="command_not_found",
    ),
    Scenario(
        rule_name="pytohn_python",
        command="pytohn -c 'print(\"hello\")'",
        output="bash: pytohn: command not found\n",
        expected_correction="python -c 'print(\"hello\")'",
        category="command_not_found",
    ),
    Scenario(
        rule_name="ndoe_node",
        command="ndoe app.js",
        output="bash: ndoe: command not found\n",
        expected_correction="node app.js",
        category="command_not_found",
    ),
    Scenario(
        rule_name="ndoe_node",
        command="ndoe --version",
        output="bash: ndoe: command not found\n",
        expected_correction="node --version",
        category="command_not_found",
    ),
    Scenario(
        rule_name="dcoker_docker",
        command="dcoker ps",
        output="bash: dcoker: command not found\n",
        expected_correction="docker ps",
        category="command_not_found",
    ),
    Scenario(
        rule_name="dcoker_docker",
        command="dcoker build -t myapp .",
        output="bash: dcoker: command not found\n",
        expected_correction="docker build -t myapp .",
        category="command_not_found",
    ),
    Scenario(
        rule_name="kubeclt_kubectl",
        command="kubeclt get pods",
        output="bash: kubeclt: command not found\n",
        expected_correction="kubectl get pods",
        category="command_not_found",
    ),
    Scenario(
        rule_name="kubeclt_kubectl",
        command="kubeclt apply -f deployment.yaml",
        output="bash: kubeclt: command not found\n",
        expected_correction="kubectl apply -f deployment.yaml",
        category="command_not_found",
    ),
    Scenario(
        rule_name="teh_the",
        command="teh quick brown fox",
        output="bash: teh: command not found\n",
        expected_correction="the quick brown fox",
        category="command_not_found",
    ),
    Scenario(
        rule_name="grpe_grep",
        command="grpe -r pattern src/",
        output="bash: grpe: command not found\n",
        expected_correction="grep -r pattern src/",
        category="command_not_found",
    ),
    Scenario(
        rule_name="maek_make",
        command="maek build",
        output="bash: maek: command not found\n",
        expected_correction="make build",
        category="command_not_found",
    ),
    Scenario(
        rule_name="maek_make",
        command="maek clean",
        output="bash: maek: command not found\n",
        expected_correction="make clean",
        category="command_not_found",
    ),
    Scenario(
        rule_name="carog_cargo",
        command="carog build",
        output="bash: carog: command not found\n",
        expected_correction="cargo build",
        category="command_not_found",
    ),
    Scenario(
        rule_name="carog_cargo",
        command="carog test",
        output="bash: carog: command not found\n",
        expected_correction="cargo test",
        category="command_not_found",
    ),
    Scenario(
        rule_name="dc_docker_compose",
        command="dc up -d",
        output="bash: dc: command not found\n",
        expected_correction="docker compose up -d",
        category="command_not_found",
    ),
    Scenario(
        rule_name="dc_docker_compose",
        command="dc down",
        output="bash: dc: command not found\n",
        expected_correction="docker compose down",
        category="command_not_found",
    ),
    Scenario(
        rule_name="apt_search",
        command="apt search vim",
        output=(
            "N: This command is deprecated. Please use 'apt-cache search' instead.\n"
            "E: Invalid operation search\n"
        ),
        expected_correction="apt-cache search vim",
        category="command_not_found",
    ),
    Scenario(
        rule_name="vim_vi",
        command="vi myfile.txt",
        output="bash: vi: command not found\n",
        expected_correction="vim myfile.txt",
        category="command_not_found",
    ),
    Scenario(
        rule_name="nano_not_found",
        command="nano myfile.txt",
        output="bash: nano: command not found\n",
        expected_correction="vim myfile.txt",
        category="command_not_found",
    ),
    Scenario(
        rule_name="wget_curl",
        command="wget https://example.com/file.tar.gz",
        output="bash: wget: command not found\n",
        expected_correction="curl -O https://example.com/file.tar.gz",
        category="command_not_found",
    ),
    Scenario(
        rule_name="curl_wget",
        command="curl -O https://example.com/file.tar.gz",
        output="bash: curl: command not found\n",
        expected_correction="wget https://example.com/file.tar.gz",
        category="command_not_found",
    ),
    Scenario(
        rule_name="open_xdg",
        command="open myfile.pdf",
        output="bash: open: command not found\n",
        expected_correction="xdg-open myfile.pdf",
        category="command_not_found",
    ),
    Scenario(
        rule_name="pbcopy_xclip",
        command="echo hello | pbcopy",
        output="bash: pbcopy: command not found\n",
        expected_correction="echo hello | xclip -selection clipboard",
        category="command_not_found",
    ),
    Scenario(
        rule_name="ifconfig_ip",
        command="ifconfig",
        output="bash: ifconfig: command not found\n",
        expected_correction="ip addr show",
        category="command_not_found",
    ),
    Scenario(
        rule_name="netstat_ss",
        command="netstat -tlnp",
        output="bash: netstat: command not found\n",
        expected_correction="ss -tlnp",
        category="command_not_found",
    ),
    Scenario(
        rule_name="service_systemctl",
        command="service nginx start",
        output="bash: service: command not found\n",
        expected_correction="sudo systemctl start nginx",
        category="command_not_found",
    ),
    Scenario(
        rule_name="service_systemctl",
        command="service postgresql restart",
        output="bash: service: command not found\n",
        expected_correction="sudo systemctl restart postgresql",
        category="command_not_found",
    ),
    Scenario(
        rule_name="python2_python",
        command="python2 script.py",
        output="bash: python2: command not found\n",
        expected_correction="python script.py",
        category="command_not_found",
    ),
    # --- fish shell typo suggestions ---
    Scenario(
        rule_name="fish_typo_exitr",
        command="exitr",
        output="fish: Unknown command. 'exitr' exists as a function but Fish cannot find it.\n",
        expected_correction="exit",
        category="command_not_found",
    ),
    Scenario(
        rule_name="fish_typo_clera",
        command="clera",
        output="fish: Unknown command. Did you mean 'clear'?\n",
        expected_correction="clear",
        category="command_not_found",
    ),
    Scenario(
        rule_name="fish_typo_htop",
        command="hto",
        output="fish: Unknown command. Did you mean 'htop'?\n",
        expected_correction="htop",
        category="command_not_found",
    ),
    Scenario(
        rule_name="fish_typo_javac",
        command="javacv",
        output="fish: Unknown command. Did you mean 'javac'?\n",
        expected_correction="javac",
        category="command_not_found",
    ),
    Scenario(
        rule_name="fish_typo_javac",
        command="javca",
        output="fish: Unknown command. Did you mean 'javac'?\n",
        expected_correction="javac",
        category="command_not_found",
    ),
    Scenario(
        rule_name="fish_typo_cargo",
        command="carg build",
        output="fish: Unknown command. Did you mean 'cargo'?\n",
        expected_correction="cargo build",
        category="command_not_found",
    ),
    Scenario(
        rule_name="fish_typo_systemctl",
        command="systemclt status sshd",
        output="fish: Unknown command. Did you mean 'systemctl'?\n",
        expected_correction="systemctl status sshd",
        category="command_not_found",
    ),
    Scenario(
        rule_name="fish_typo_fastfetch",
        command="fasfetch",
        output="fish: Unknown command. Did you mean 'fastfetch'?\n",
        expected_correction="fastfetch",
        category="command_not_found",
    ),
]

# ---------------------------------------------------------------------------
# PERMISSION / SUDO SCENARIOS
# ---------------------------------------------------------------------------

PERMISSION_SCENARIOS: list[Scenario] = [
    Scenario(
        rule_name="no_such_file",
        command="cat /var/log/syslog",
        output="cat: /var/log/syslog: Permission denied\n",
        expected_correction="sudo cat /var/log/syslog",
        category="permissions",
    ),
    Scenario(
        rule_name="no_such_file",
        command="cat /etc/shadow",
        output="cat: /etc/shadow: Permission denied\n",
        expected_correction="sudo cat /etc/shadow",
        category="permissions",
    ),
    Scenario(
        rule_name="sudo_command",
        command="systemctl restart nginx",
        output=(
            "Failed to restart nginx.service: Access denied\n"
            "See system logs and 'systemctl status nginx.service' for details.\n"
        ),
        expected_correction="sudo systemctl restart nginx",
        category="permissions",
    ),
    Scenario(
        rule_name="sudo_command",
        command="systemctl start postgresql",
        output=(
            "Failed to start postgresql.service: Access denied\n"
            "See system logs and 'systemctl status postgresql.service' for details.\n"
        ),
        expected_correction="sudo systemctl start postgresql",
        category="permissions",
    ),
    Scenario(
        rule_name="sudo_command",
        command="systemctl stop redis",
        output=(
            "Failed to stop redis.service: Access denied\n"
            "See system logs and 'systemctl status redis.service' for details.\n"
        ),
        expected_correction="sudo systemctl stop redis",
        category="permissions",
    ),
    Scenario(
        rule_name="sudo_command",
        command="systemctl enable nginx",
        output=(
            "Failed to enable unit: Access denied\n"
        ),
        expected_correction="sudo systemctl enable nginx",
        category="permissions",
    ),
    Scenario(
        rule_name="mkdir_permission",
        command="mkdir /opt/myapp",
        output="mkdir: cannot create directory '/opt/myapp': Permission denied\n",
        expected_correction="sudo mkdir /opt/myapp",
        category="permissions",
    ),
    Scenario(
        rule_name="mkdir_permission",
        command="mkdir /usr/local/lib/mylib",
        output="mkdir: cannot create directory '/usr/local/lib/mylib': Permission denied\n",
        expected_correction="sudo mkdir /usr/local/lib/mylib",
        category="permissions",
    ),
    Scenario(
        rule_name="touch_permission",
        command="touch /etc/myconfig.conf",
        output="touch: cannot touch '/etc/myconfig.conf': Permission denied\n",
        expected_correction="sudo touch /etc/myconfig.conf",
        category="permissions",
    ),
    Scenario(
        rule_name="touch_permission",
        command="touch /etc/cron.d/myjob",
        output="touch: cannot touch '/etc/cron.d/myjob': Permission denied\n",
        expected_correction="sudo touch /etc/cron.d/myjob",
        category="permissions",
    ),
    Scenario(
        rule_name="lsof_port",
        command="lsof -i :8080",
        output=(
            "lsof: WARNING: can't stat() fuse.portal file system\n"
            "      Output information may be incomplete.\n"
        ),
        expected_correction="sudo lsof -i :8080",
        category="permissions",
    ),
    Scenario(
        rule_name="lsof_port",
        command="lsof -i :3000",
        output=(
            "lsof: WARNING: can't stat() fuse.portal file system\n"
            "      Output information may be incomplete.\n"
        ),
        expected_correction="sudo lsof -i :3000",
        category="permissions",
    ),
    Scenario(
        rule_name="ssh_permission",
        command="ssh user@host",
        output=(
            "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n"
            "@         WARNING: UNPROTECTED PRIVATE KEY FILE!          @\n"
            "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n"
            "Permissions 0644 for '/home/user/.ssh/id_rsa' are too open.\n"
        ),
        expected_correction="chmod 600 ~/.ssh/id_rsa && ssh user@host",
        category="permissions",
    ),
    Scenario(
        rule_name="ssh_permission",
        command="ssh alice@server01",
        output=(
            "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n"
            "@         WARNING: UNPROTECTED PRIVATE KEY FILE!          @\n"
            "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n"
            "Permissions 0640 for '/home/alice/.ssh/id_ed25519' are too open.\n"
        ),
        expected_correction="chmod 600 ~/.ssh/id_ed25519 && ssh alice@server01",
        category="permissions",
    ),
    Scenario(
        rule_name="docker_permission",
        command="docker ps",
        output=(
            "permission denied while trying to connect to the Docker daemon socket "
            "at unix:///var/run/docker.sock: Get \"http://%2Fvar%2Frun%2Fdocker.sock/v1.24/containers/json\": "
            "dial unix /var/run/docker.sock: connect: permission denied\n"
        ),
        expected_correction=[
            "sudo docker ps",
            "sudo usermod -aG docker $USER",
        ],
        category="permissions",
    ),
    Scenario(
        rule_name="write_permission",
        command="echo 'hello' > /etc/motd",
        output="bash: /etc/motd: Permission denied\n",
        expected_correction="sudo sh -c 'echo hello > /etc/motd'",
        category="permissions",
    ),
    Scenario(
        rule_name="apt_permission_update",
        command="apt update",
        output="E: Could not open lock file /var/lib/apt/lists/lock - open (13: Permission denied)\n",
        expected_correction="sudo apt update",
        category="permissions",
    ),
    Scenario(
        rule_name="pip_install_system",
        command="pip install requests",
        output=(
            "error: externally-managed-environment\n\n"
            "× This environment is externally managed\n"
            "╰─> To install Python packages system-wide, try apt install\n"
            "    python3-xyz, where xyz is the package you are trying to\n"
            "    install.\n"
        ),
        expected_correction="pip install --break-system-packages requests",
        category="permissions",
    ),
    # --- pacman without sudo (various operations) ---
    Scenario(
        rule_name="pacman_permission",
        command="pacman -S git",
        output="error: you cannot perform this operation unless you are root.\n",
        expected_correction="sudo pacman -S git",
        category="permissions",
    ),
    Scenario(
        rule_name="pacman_permission",
        command="pacman -S openssh",
        output="error: you cannot perform this operation unless you are root.\n",
        expected_correction="sudo pacman -S openssh",
        category="permissions",
    ),
    Scenario(
        rule_name="pacman_permission",
        command="pacman -S discord",
        output="error: you cannot perform this operation unless you are root.\n",
        expected_correction="sudo pacman -S discord",
        category="permissions",
    ),
    Scenario(
        rule_name="pacman_permission",
        command="pacman -Rns firefox",
        output="error: you cannot perform this operation unless you are root.\n",
        expected_correction="sudo pacman -Rns firefox",
        category="permissions",
    ),
    Scenario(
        rule_name="pacman_permission",
        command="pacman -S pavucontrol",
        output="error: you cannot perform this operation unless you are root.\n",
        expected_correction="sudo pacman -S pavucontrol",
        category="permissions",
    ),
    # --- system admin tools without sudo ---
    Scenario(
        rule_name="mkinitcpio_permission",
        command="mkinitcpio -P",
        output="==> ERROR: You must be root to run this program.\n",
        expected_correction="sudo mkinitcpio -P",
        category="permissions",
    ),
    Scenario(
        rule_name="mkinitcpio_permission",
        command="mkinitcpio -p linux",
        output="==> ERROR: You must be root to run this program.\n",
        expected_correction="sudo mkinitcpio -p linux",
        category="permissions",
    ),
    Scenario(
        rule_name="sbctl_permission",
        command="sbctl enroll-keys --microsoft",
        output="sbctl requires root to run\n",
        expected_correction="sudo sbctl enroll-keys --microsoft",
        category="permissions",
    ),
    Scenario(
        rule_name="sbctl_permission",
        command="sbctl create-keys",
        output="sbctl requires root to run\n",
        expected_correction="sudo sbctl create-keys",
        category="permissions",
    ),
    Scenario(
        rule_name="sbctl_permission",
        command="sbctl status",
        output="sbctl requires root to run\n",
        expected_correction="sudo sbctl status",
        category="permissions",
    ),
    Scenario(
        rule_name="snapper_permission",
        command="snapper -c root create-config /",
        output="IO Error (permission denied).\n",
        expected_correction="sudo snapper -c root create-config /",
        category="permissions",
    ),
    Scenario(
        rule_name="snapper_permission",
        command="snapper create --description backup",
        output="IO Error (permission denied).\n",
        expected_correction="sudo snapper create --description backup",
        category="permissions",
    ),
    Scenario(
        rule_name="btrfs_permission",
        command="btrfs subvolume list /",
        output=(
            "ERROR: can't perform the search - Operation not permitted\n"
            "ERROR: can't list subvolumes: Operation not permitted\n"
        ),
        expected_correction="sudo btrfs subvolume list /",
        category="permissions",
    ),
    Scenario(
        rule_name="grub_permission",
        command="grub-mkconfig -o /boot/grub/grub.cfg",
        output="grub-mkconfig: You must run this as root\n",
        expected_correction="sudo grub-mkconfig -o /boot/grub/grub.cfg",
        category="permissions",
    ),
]

# ---------------------------------------------------------------------------
# NETWORK / SERVICE SCENARIOS
# ---------------------------------------------------------------------------

NETWORK_SCENARIOS: list[Scenario] = [
    Scenario(
        rule_name="docker_not_running",
        command="docker ps",
        output=(
            "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
            "Is the docker daemon running?\n"
        ),
        expected_correction="sudo systemctl start docker && docker ps",
        category="network",
    ),
    Scenario(
        rule_name="docker_not_running",
        command="docker build -t myapp .",
        output=(
            "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
            "Is the docker daemon running?\n"
        ),
        expected_correction="sudo systemctl start docker && docker build -t myapp .",
        category="network",
    ),
    Scenario(
        rule_name="port_in_use",
        command="python -m http.server 8080",
        output="OSError: [Errno 98] Address already in use\n",
        expected_correction="python -m http.server 8081",
        category="network",
    ),
    Scenario(
        rule_name="port_in_use",
        command="python -m http.server 3000",
        output="OSError: [Errno 98] Address already in use\n",
        expected_correction="python -m http.server 3001",
        category="network",
    ),
    Scenario(
        rule_name="port_in_use_kill",
        command="python app.py",
        output="OSError: [Errno 98] Address already in use\nPort 5000 is already in use.\n",
        expected_correction=[
            "fuser -k 5000/tcp && python app.py",
            "lsof -ti:5000 | xargs kill && python app.py",
        ],
        category="network",
    ),
    Scenario(
        rule_name="connection_refused",
        command="curl http://localhost:8080/api",
        output="curl: (7) Failed to connect to localhost port 8080 after 0 ms: Connection refused\n",

        category="network",
    ),
    Scenario(
        rule_name="dns_failed",
        command="curl https://nonexistent-domain-xyz.example.com",
        output="curl: (6) Could not resolve host: nonexistent-domain-xyz.example.com\n",

        category="network",
    ),
    Scenario(
        rule_name="ssh_connection_refused",
        command="ssh user@192.168.1.100",
        output="ssh: connect to host 192.168.1.100 port 22: Connection refused\n",

        category="network",
    ),
    Scenario(
        rule_name="ssh_timeout",
        command="ssh user@10.0.0.5",
        output="ssh: connect to host 10.0.0.5 port 22: Connection timed out\n",

        category="network",
    ),
    Scenario(
        rule_name="ssh_host_changed",
        command="ssh user@server01",
        output=(
            "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n"
            "@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @\n"
            "@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@\n"
            "IT IS POSSIBLE THAT SOMEONE IS DOING SOMETHING NASTY!\n"
            "Host key for server01 has changed and you have requested strict checking.\n"
        ),
        expected_correction="ssh-keygen -R server01 && ssh user@server01",
        category="network",
    ),
    Scenario(
        rule_name="postgres_not_running",
        command="psql -U postgres",
        output="psql: error: connection to server on socket \"/var/run/postgresql/.s.PGSQL.5432\" failed: No such file or directory\n",
        expected_correction="sudo systemctl start postgresql && psql -U postgres",
        category="network",
    ),
    Scenario(
        rule_name="redis_not_running",
        command="redis-cli ping",
        output="Could not connect to Redis at 127.0.0.1:6379: Connection refused\n",
        expected_correction="sudo systemctl start redis && redis-cli ping",
        category="network",
    ),
    Scenario(
        rule_name="port_in_use_node",
        command="npm start",
        output=(
            "Error: listen EADDRINUSE: address already in use :::3000\n"
            "    at Server.setupListenHandle [as _listen2] (node:net:1855:16)\n"
        ),
        expected_correction=[
            "fuser -k 3000/tcp && npm start",
            "lsof -ti:3000 | xargs kill && npm start",
        ],
        category="network",
    ),
    Scenario(
        rule_name="curl_ssl",
        command="curl https://self-signed.example.com/api",
        output=(
            "curl: (60) SSL certificate problem: self-signed certificate\n"
            "More details here: https://curl.se/docs/sslcerts.html\n"
        ),
        expected_correction="curl -k https://self-signed.example.com/api",
        category="network",
    ),
]

# ---------------------------------------------------------------------------
# PYTHON / NODE RUNTIME SCENARIOS
# ---------------------------------------------------------------------------

RUNTIME_SCENARIOS: list[Scenario] = [
    Scenario(
        rule_name="python_syntax_error",
        command="python script.py",
        output=(
            "  File 'script.py', line 5\n"
            "    def foo(\n"
            "           ^\n"
            "SyntaxError: '(' was never closed\n"
        ),

        category="runtime",
    ),
    Scenario(
        rule_name="python_syntax_error",
        command="python app.py",
        output=(
            "  File 'app.py', line 12\n"
            "    if x = 5:\n"
            "         ^\n"
            "SyntaxError: invalid syntax. Did you mean '=='?\n"
        ),

        category="runtime",
    ),
    Scenario(
        rule_name="python_file_not_found",
        command="python nonexistent.py",
        output="python: can't open file '/home/user/nonexistent.py': [Errno 2] No such file or directory\n",

        category="runtime",
    ),
    Scenario(
        rule_name="python_version_mismatch",
        command="python script.py",
        output=(
            "  File 'script.py', line 1\n"
            "    print 'hello'\n"
            "    ^^^^^^^^^^^^^^\n"
            "SyntaxError: Missing parentheses in call to 'print'. Did you mean print(...)?\n"
        ),
        category="runtime",
    ),
    Scenario(
        rule_name="node_module_not_found",
        command="node app.js",
        output=(
            "node:internal/modules/cjs/loader:1051\n"
            "  throw err;\n"
            "  ^\n"
            "Error: Cannot find module 'express'\n"
            "Require stack:\n"
            "- /home/user/app.js\n"
        ),
        expected_correction="npm install express && node app.js",
        category="runtime",
    ),
    Scenario(
        rule_name="node_module_not_found",
        command="node server.js",
        output=(
            "node:internal/modules/cjs/loader:1051\n"
            "  throw err;\n"
            "  ^\n"
            "Error: Cannot find module 'axios'\n"
            "Require stack:\n"
            "- /home/user/server.js\n"
        ),
        expected_correction="npm install axios && node server.js",
        category="runtime",
    ),
    Scenario(
        rule_name="node_module_not_found",
        command="node index.js",
        output=(
            "Error: Cannot find module 'dotenv'\n"
            "Require stack:\n"
            "- /home/user/index.js\n"
        ),
        expected_correction="npm install dotenv && node index.js",
        category="runtime",
    ),
    Scenario(
        rule_name="node_version_error",
        command="node app.js",
        output=(
            "/home/user/app.js:1\n"
            "const { pipeline } = require('stream/promises');\n"
            "Error [ERR_MODULE_NOT_FOUND]: Cannot find module 'stream/promises'\n"
            "Node version requirement: >=16.0.0\n"
        ),

        category="runtime",
    ),
    Scenario(
        rule_name="ts_compile_error",
        command="tsc --noEmit",
        output=(
            "src/app.ts:10:5 - error TS2345: Argument of type 'string' is not assignable to parameter of type 'number'.\n"
            "\n"
            "Found 1 error.\n"
        ),

        category="runtime",
    ),
    Scenario(
        rule_name="python_import_circular",
        command="python main.py",
        output=(
            "Traceback (most recent call last):\n"
            "  File 'main.py', line 1, in <module>\n"
            "    from models import User\n"
            "  File 'models.py', line 1, in <module>\n"
            "    from main import app\n"
            "ImportError: cannot import name 'app' from partially initialized module 'main'\n"
        ),

        category="runtime",
    ),
]

# ---------------------------------------------------------------------------
# GENERAL / MISCELLANEOUS SCENARIOS
# ---------------------------------------------------------------------------

GENERAL_SCENARIOS: list[Scenario] = [
    Scenario(
        rule_name="grep_r",
        command="grep -r pattern",
        output="grep: warning: recursive search of stdin\n",
        expected_correction="grep -r pattern .",
        category="general",
    ),
    Scenario(
        rule_name="grep_no_match",
        command="grep -r 'nonexistentstring12345' src/",
        output="",

        category="general",
    ),
    Scenario(
        rule_name="make_no_target",
        command="make biuld",
        output="make: *** No rule to make target 'biuld'.  Stop.\n",
        expected_correction="make build",
        category="general",
    ),
    Scenario(
        rule_name="make_no_target",
        command="make tset",
        output="make: *** No rule to make target 'tset'.  Stop.\n",
        expected_correction="make test",
        category="general",
    ),
    Scenario(
        rule_name="make_no_target",
        command="make instal",
        output="make: *** No rule to make target 'instal'.  Stop.\n",
        expected_correction="make install",
        category="general",
    ),
    Scenario(
        rule_name="make_no_makefile",
        command="make build",
        output="make: *** No targets specified and no makefile found.  Stop.\n",

        category="general",
    ),
    Scenario(
        rule_name="man_page",
        command="man gti",
        output="No manual entry for gti\nDid you mean git?\n",
        expected_correction="man git",
        category="general",
    ),
    Scenario(
        rule_name="man_page",
        command="man pytohn",
        output="No manual entry for pytohn\n",
        expected_correction="man python",
        category="general",
    ),
    Scenario(
        rule_name="tar_extract",
        command="tar xf archive.tar.gz",
        output="tar: Refusing to create empty archive\n",
        expected_correction="tar xzf archive.tar.gz",
        category="general",
    ),
    Scenario(
        rule_name="tar_missing_z",
        command="tar -xf archive.tar.gz",
        output=(
            "gzip: stdin: not in gzip format\n"
            "tar: Child returned status 1\n"
            "tar: Error is not recoverable: exiting now\n"
        ),
        expected_correction="tar -xzf archive.tar.gz",
        category="general",
    ),
    Scenario(
        rule_name="tar_create",
        command="tar czf backup.tar.gz /home/user/docs",
        output="tar: Removing leading '/' from member names\n",
        expected_correction="tar czf backup.tar.gz -C / home/user/docs",
        category="general",
    ),
    Scenario(
        rule_name="kill_no_pid",
        command="kill 99999",
        output="bash: kill: (99999) - No such process\n",

        category="general",
    ),
    Scenario(
        rule_name="ps_grep",
        command="ps aux grep nginx",
        output="error: garbage option\n",
        expected_correction="ps aux | grep nginx",
        category="general",
    ),
    Scenario(
        rule_name="find_permission",
        command="find / -name '*.conf'",
        output=(
            "find: '/proc/tty/driver': Permission denied\n"
            "find: '/root': Permission denied\n"
        ),
        expected_correction="sudo find / -name '*.conf'",
        category="general",
    ),
    Scenario(
        rule_name="python_script_direct",
        command="script.py",
        output="bash: script.py: command not found\n",
        expected_correction="python script.py",
        category="general",
    ),
    Scenario(
        rule_name="python_script_direct",
        command="app.py",
        output="bash: app.py: command not found\n",
        expected_correction="python app.py",
        category="general",
    ),
    Scenario(
        rule_name="ruby_script_direct",
        command="server.rb",
        output="bash: server.rb: command not found\n",
        expected_correction="ruby server.rb",
        category="general",
    ),
    Scenario(
        rule_name="history_expansion",
        command="git commit -m 'fix bug #123'",
        output="bash: !123': event not found\n",
        expected_correction="git commit -m 'fix bug #123'",
        category="general",
    ),
    Scenario(
        rule_name="curl_post_json",
        command="curl -X POST http://localhost:8080/api -d '{\"key\": \"value\"}'",
        output="curl: (3) URL rejected: Port number was not a decimal number between 0 and 65535\n",

        category="general",
    ),
    Scenario(
        rule_name="jq_invalid",
        command="jq .name data.json",
        output="parse error (Invalid numeric literal at EOF on line 1, column 5): (null)\n",

        category="general",
    ),
    Scenario(
        rule_name="sed_in_place",
        command="sed -i 's/foo/bar/' file.txt",
        output="sed: 1: 'file.txt': command c expects \\ followed by text\n",
        expected_correction="sed -i '' 's/foo/bar/' file.txt",
        category="general",
    ),
    Scenario(
        rule_name="disk_full",
        command="cp large_file.iso /tmp/",
        output="cp: error writing '/tmp/large_file.iso': No space left on device\n",

        category="general",
    ),
    Scenario(
        rule_name="pip_missing_venv",
        command="pip install requests",
        output=(
            "error: externally-managed-environment\n"
            "hint: See PEP 668 for the reasons why this is disallowed.\n"
            "hint: If you want to install packages system-wide, use pipx.\n"
        ),
        expected_correction="python -m venv .venv && source .venv/bin/activate && pip install requests",
        category="general",
    ),
    # --- double sudo ---
    Scenario(
        rule_name="double_sudo",
        command="sudo sudo reboot",
        output="sudo: sudo: command not found\n",
        expected_correction="sudo reboot",
        category="general",
    ),
    Scenario(
        rule_name="double_sudo",
        command="sudo sudo pacman -Syu",
        output="sudo: sudo: command not found\n",
        expected_correction="sudo pacman -Syu",
        category="general",
    ),
    Scenario(
        rule_name="double_sudo",
        command="sudo sudo systemctl restart nginx",
        output="sudo: sudo: command not found\n",
        expected_correction="sudo systemctl restart nginx",
        category="general",
    ),
    Scenario(
        rule_name="double_sudo",
        command="sudo sudo mount /dev/sda1 /mnt",
        output="sudo: sudo: command not found\n",
        expected_correction="sudo mount /dev/sda1 /mnt",
        category="general",
    ),
    # --- wrong package names (distro confusion) ---
    Scenario(
        rule_name="pacman_wrong_pkg_name",
        command="sudo pacman -S openssh-server",
        output="error: target not found: openssh-server\n",
        expected_correction="sudo pacman -S openssh",
        category="general",
    ),
    Scenario(
        rule_name="pacman_wrong_pkg_name",
        command="sudo pacman -S sshd",
        output="error: target not found: sshd\n",
        expected_correction="sudo pacman -S openssh",
        category="general",
    ),
    Scenario(
        rule_name="pacman_wrong_pkg_name",
        command="sudo pacman -S python3",
        output="error: target not found: python3\n",
        expected_correction="sudo pacman -S python",
        category="general",
    ),
    Scenario(
        rule_name="pacman_wrong_pkg_name",
        command="sudo pacman -S python3-pip",
        output="error: target not found: python3-pip\n",
        expected_correction="sudo pacman -S python-pip",
        category="general",
    ),
    Scenario(
        rule_name="pacman_wrong_pkg_name",
        command="sudo pacman -S libssl-dev",
        output="error: target not found: libssl-dev\n",
        expected_correction="sudo pacman -S openssl",
        category="general",
    ),
    Scenario(
        rule_name="pacman_wrong_pkg_name",
        command="sudo pacman -S build-essential",
        output="error: target not found: build-essential\n",
        expected_correction="sudo pacman -S base-devel",
        category="general",
    ),
    # --- pacman package name typos ---
    Scenario(
        rule_name="pacman_pkg_typo",
        command="yay -Rns c-area",
        output="error: target not found: c-area\n",
        expected_correction="yay -Rns c-ares",
        category="general",
    ),
    Scenario(
        rule_name="pacman_pkg_typo",
        command="sudo pacman -S fierfox",
        output="error: target not found: fierfox\n",
        expected_correction="sudo pacman -S firefox",
        category="general",
    ),
    Scenario(
        rule_name="pacman_pkg_typo",
        command="sudo pacman -S libreofice",
        output="error: target not found: libreofice\n",
        expected_correction="sudo pacman -S libreoffice-fresh",
        category="general",
    ),
    Scenario(
        rule_name="pacman_pkg_typo",
        command="sudo pacman -S htpo",
        output="error: target not found: htpo\n",
        expected_correction="sudo pacman -S htop",
        category="general",
    ),
]

# ---------------------------------------------------------------------------
# DOCKER SCENARIOS
# ---------------------------------------------------------------------------

DOCKER_SCENARIOS: list[Scenario] = [
    Scenario(
        rule_name="docker_not_running",
        command="docker images",
        output=(
            "Cannot connect to the Docker daemon at unix:///var/run/docker.sock. "
            "Is the docker daemon running?\n"
        ),
        expected_correction=[
            "sudo systemctl start docker && docker images",
            "sudo dockerd &",
        ],
        category="docker",
    ),
    Scenario(
        rule_name="docker_image_not_found",
        command="docker run nonexistent-image:latest",
        output=(
            "Unable to find image 'nonexistent-image:latest' locally\n"
            "docker: Error response from daemon: pull access denied for nonexistent-image, "
            "repository does not exist or may require 'docker login'\n"
        ),

        category="docker",
    ),
    Scenario(
        rule_name="docker_port_used",
        command="docker run -p 8080:80 nginx",
        output=(
            "docker: Error response from daemon: driver failed programming external connectivity on endpoint "
            "vigorous_johnson: Bind for 0.0.0.0:8080 failed: port is already allocated.\n"
        ),
        expected_correction="docker run -p 8081:80 nginx",
        category="docker",
    ),
    Scenario(
        rule_name="docker_container_not_found",
        command="docker exec -it mycontainer bash",
        output="Error response from daemon: No such container: mycontainer\n",

        category="docker",
    ),
    Scenario(
        rule_name="docker_compose_not_found",
        command="docker-compose up -d",
        output="bash: docker-compose: command not found\n",
        expected_correction="docker compose up -d",
        category="docker",
    ),
    Scenario(
        rule_name="docker_compose_not_found",
        command="docker-compose down",
        output="bash: docker-compose: command not found\n",
        expected_correction="docker compose down",
        category="docker",
    ),
    Scenario(
        rule_name="docker_compose_no_file",
        command="docker compose up -d",
        output=(
            'can\'t find a suitable configuration file in this directory or any\n'
            'parent: not found\n'
            'Consider using the `-f` flag to specify a configuration file or the\n'
            '`--project-directory` flag to specify a root search path.\n'
        ),

        category="docker",
    ),
    Scenario(
        rule_name="docker_build_no_dockerfile",
        command="docker build -t myapp .",
        output=(
            "ERROR: failed to solve: failed to read dockerfile: open Dockerfile: no such file or directory\n"
        ),

        category="docker",
    ),
    Scenario(
        rule_name="docker_login_required",
        command="docker pull private-registry.example.com/myimage:latest",
        output=(
            "Error response from daemon: Head 'https://private-registry.example.com/v2/myimage/manifests/latest': "
            "unauthorized: authentication required\n"
        ),
        expected_correction="docker login private-registry.example.com && docker pull private-registry.example.com/myimage:latest",
        category="docker",
    ),
]

# ---------------------------------------------------------------------------
# KUBERNETES SCENARIOS
# ---------------------------------------------------------------------------

KUBERNETES_SCENARIOS: list[Scenario] = [
    Scenario(
        rule_name="kubectl_not_found",
        command="kubeclt get pods",
        output="bash: kubeclt: command not found\n",
        expected_correction="kubectl get pods",
        category="kubernetes",
    ),
    Scenario(
        rule_name="kubectl_context",
        command="kubectl get pods",
        output=(
            "error: the server doesn't have a resource type 'pods'\n"
            "The connection to the server localhost:8080 was refused - did you specify the right host or port?\n"
        ),

        category="kubernetes",
    ),
    Scenario(
        rule_name="kubectl_namespace",
        command="kubectl get pods myapp",
        output='Error from server (NotFound): pods "myapp" not found\n',
        expected_correction="kubectl get pods -A | grep myapp",
        category="kubernetes",
    ),
    Scenario(
        rule_name="kubectl_apply",
        command="kubectl apply -f deployment.yml",
        output=(
            "error: error parsing deployment.yml: error converting YAML to JSON: "
            "yaml: line 5: mapping values are not allowed in this context\n"
        ),

        category="kubernetes",
    ),
    Scenario(
        rule_name="kubectl_typo",
        command="kubectl get deployemnt",
        output=(
            'error: the server doesn\'t have a resource type "deployemnt"\n'
            "Did you mean 'deployment'?\n"
        ),
        expected_correction="kubectl get deployment",
        category="kubernetes",
    ),
]

# ---------------------------------------------------------------------------
# ORIGINAL SCENARIOS (kept for backward compat)
# ---------------------------------------------------------------------------

SCENARIOS: list[Scenario] = (
    GIT_SCENARIOS
    + PACKAGE_MANAGER_SCENARIOS
    + FILE_SCENARIOS
    + COMMAND_NOT_FOUND_SCENARIOS
    + PERMISSION_SCENARIOS
    + NETWORK_SCENARIOS
    + RUNTIME_SCENARIOS
    + GENERAL_SCENARIOS
    + DOCKER_SCENARIOS
    + KUBERNETES_SCENARIOS
)

# Negative examples: commands that are unfixable.
NEGATIVE_SCENARIOS: list[Scenario] = [
    Scenario(
        rule_name="negative",
        command="asdfghjkl",
        output="bash: asdfghjkl: command not found\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="xyzzy --foo --bar",
        output="bash: xyzzy: command not found\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="echo hello",
        output="hello\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="ls",
        output="file1.txt  file2.txt  src/\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="qqq rrr sss ttt",
        output="bash: qqq: command not found\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="./nonexistent_binary --help",
        output="bash: ./nonexistent_binary: No such file or directory\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="cat",
        output="",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="true",
        output="",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="aaa bbb ccc ddd eee",
        output="bash: aaa: command not found\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="zzznotacommand --version",
        output="bash: zzznotacommand: command not found\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="git push --force origin main",
        output="Everything up-to-date\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="pwd",
        output="/home/user/projects\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="date",
        output="Mon Jan  1 00:00:00 UTC 2024\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="whoami",
        output="user\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="flibbertigibbet --config foo.yaml run",
        output="bash: flibbertigibbet: command not found\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="python script.py",
        output="Traceback (most recent call last):\n  File 'script.py', line 42, in main\n    result = compute(x, y)\nValueError: math domain error\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="git log",
        output=(
            "commit abc1234def5678 (HEAD -> main, origin/main)\n"
            "Author: Alice <alice@example.com>\n"
            "Date:   Mon Jan  1 00:00:00 2024 +0000\n\n"
            "    initial commit\n"
        ),

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="docker ps",
        output=(
            "CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES\n"
        ),

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="kubectl get pods",
        output="No resources found in default namespace.\n",

        category="negative",
    ),
    Scenario(
        rule_name="negative",
        command="npm install",
        output=(
            "added 1234 packages, and audited 1235 packages in 30s\n"
            "found 0 vulnerabilities\n"
        ),

        category="negative",
    ),
]


def try_thefuck_rule(rule_name: str, command_str: str, output: str) -> str | None:
    """Try to invoke a thefuck rule dynamically and return the correction.

    Returns None if the rule can't be loaded or doesn't match.
    """
    try:
        mod = importlib.import_module(f"thefuck.rules.{rule_name}")
    except (ImportError, ModuleNotFoundError):
        return None

    if not hasattr(mod, "match") or not hasattr(mod, "get_new_command"):
        return None

    # Build a minimal Command object. We avoid importing from thefuck.types
    # to reduce dependency on thefuck internals that may require shell init.
    class MinimalCommand:
        def __init__(self, script, output):
            self.script = script
            self.output = output

        @property
        def script_parts(self):
            return self.script.split()

    cmd = MinimalCommand(command_str, output)

    try:
        if mod.match(cmd):
            result = mod.get_new_command(cmd)
            if isinstance(result, list):
                return result[0]
            return result
    except Exception:
        pass

    return None


def generate_examples(use_thefuck: bool = True) -> list[dict]:
    """Generate all training examples.

    Args:
        use_thefuck: If True, try to use thefuck rules dynamically for corrections.
                     Falls back to curated corrections either way.

    Returns:
        List of {"command": ..., "stderr": ..., "correction": ...} dicts.
    """
    examples = []

    for scenario in SCENARIOS + NEGATIVE_SCENARIOS:
        correction = scenario.expected_correction

        # Normalize list corrections to newline-separated string
        if isinstance(correction, list):
            correction = "\n".join(correction)

        if use_thefuck and correction is not None:
            dynamic = try_thefuck_rule(
                scenario.rule_name, scenario.command, scenario.output
            )
            if dynamic:
                correction = dynamic

        examples.append(
            {
                "command": scenario.command,
                "stderr": scenario.output.strip(),
                "correction": correction if correction is not None else "?",
            }
        )

    return examples


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic training data from thefuck rules"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("data/base_examples.jsonl"),
        help="Output JSONL file path (default: data/base_examples.jsonl)",
    )
    parser.add_argument(
        "--no-thefuck",
        action="store_true",
        help="Don't try to use thefuck rules dynamically, use curated corrections only",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print statistics about generated data",
    )
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)

    examples = generate_examples(use_thefuck=not args.no_thefuck)

    with open(args.output, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")

    n_positive = sum(1 for ex in examples if ex["correction"] != "?")
    n_negative = sum(1 for ex in examples if ex["correction"] == "?")
    total = len(examples)

    print(f"Generated {total} examples ({n_positive} positive, {n_negative} negative)")
    print(f"Negative ratio: {n_negative / total:.1%}")
    print(f"Written to {args.output}")

    if args.stats:
        # Count by category
        categories: dict[str, int] = {}
        n_multi = 0
        for s in SCENARIOS + NEGATIVE_SCENARIOS:
            categories[s.category] = categories.get(s.category, 0) + 1
            if isinstance(s.expected_correction, list):
                n_multi += 1
        print("\nBy category:")
        for cat, count in sorted(categories.items()):
            print(f"  {cat}: {count}")
        print(f"\nMulti-alternative scenarios: {n_multi}")


if __name__ == "__main__":
    main()
