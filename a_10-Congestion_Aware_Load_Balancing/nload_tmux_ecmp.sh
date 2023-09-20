#!/usr/bin/env bash

tmux split-window -h
tmux select-pane -t 0
tmux split-window -v

tmux select-pane -t 2
tmux split-window -v


tmux select-pane -t 0
tmux send "nload s2-eth1" ENTER

tmux select-pane -t 1
tmux send "nload s3-eth1" ENTER

tmux select-pane -t 2
tmux send "nload s4-eth1" ENTER

tmux select-pane -t 3
tmux send "nload s5-eth1" ENTER

