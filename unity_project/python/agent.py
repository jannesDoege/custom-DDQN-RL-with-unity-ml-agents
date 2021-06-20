import torch
import torch.nn as nn
import torch.functional as F
from torch.autograd import Variable
import copy
import numpy as np
import random

import model
import buffer
import hyperparams

device = "cuda" if torch.cuda.is_available() else "cpu"
print(device)

class Agent:
    def __init__(self, sync_frame, buffer_length: int, action_size, observation_size, discount_factor=0.99, learning_rate=1e-3, batch_size=64, update_rate=4):
        self.t_frame=0
        self.t_step=0
        self.sync_frame = sync_frame
        self.action_size=action_size
        self.observation_size=observation_size
        self.discount_factor=discount_factor
        self.lr = learning_rate
        self.batch_size = batch_size
        self.buffer_length = buffer_length
        self.update_rate = update_rate

        self.net = model.DQN(observation_size, action_size).to(device)
        self.target_net = copy.deepcopy(self.net)
        self.rep_buffer = buffer.ReplayBuffer(capacity=self.buffer_length)
        self.optimizer = torch.optim.Adam(self.net.parameters(), lr=self.lr)

    def step(self, observation: buffer.Experience):
        self.rep_buffer.add_exp(observation)
        
        self.t_frame+=1

        if len(self.rep_buffer) == self.buffer_length:
            return self.learn()
        
    def act(self, state, eps):
        state = torch.tensor(state).to(device)
        with torch.no_grad():
            actions = self.net(state).max(-1)[1]

        if random.random() > eps:
            return actions
        else: return random.choice(np.arange(self.action_size))

    def learn(self):
        loss_v = self.calc_loss()
        loss_v = Variable(loss_v.data, requires_grad = True)

        self.optimizer.zero_grad()
        loss_v.backward()
        self.optimizer.step()
        self.target_net_update()
        
        return loss_v


    def target_net_update(self):
        if self.t_frame % self.sync_frame == 0:
            self.target_net.load_state_dict(self.net.state_dict())

    def calc_loss(self):
        states, actions, rewards, dones, next_states = self.rep_buffer.sample(batch_size=self.batch_size)
        
        states_v = torch.tensor(np.array(states, copy=False)).to(device)
        next_states_v = torch.tensor(np.array(next_states, copy=False)).to(device)
        actions_v = torch.tensor(np.array(actions, copy=False,  dtype=np.float32)).to(device)
        rewards_v = torch.tensor(np.array(rewards, copy=False, dtype=np.float32)).to(device)
        dones_mask = torch.BoolTensor(dones).to(device)
        
        actions_v = actions_v.unsqueeze(-1)
        actions_v = actions_v.to(torch.int64)
        actions_v = actions_v.to(device)
        state_action_vals = torch.gather(self.net(states_v), -1, actions_v).squeeze(-1)

        with torch.no_grad():            
            next_state_actions = self.net(next_states_v).max(1)[1].unsqueeze(-1)
            next_state_values = self.target_net(next_states_v).gather(1, next_state_actions).squeeze(-1)
            next_state_values[dones_mask] = 0.0

            qsa_targets = rewards_v + self.discount_factor * next_state_values.detach()
            lsc = torch.nn.MSELoss()

            loss = lsc(state_action_vals, qsa_targets)
            return loss
