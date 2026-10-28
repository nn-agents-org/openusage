# remote add origin https://github.com/nn-agents-org/openusage.git
git fetch upstream
git checkout main
git merge upstream/main
git push origin main
git checkout feature/menu-bar-agent-icons
git rebase main
git push --force-with-lease origin feature/menu-bar-agent-icons