# Copyright 2021 Tencent
# SPDX-License-Identifier: BSD-3-Clause

import torch
import torch.nn as nn
import torch.nn.functional as F

class Model(nn.Module):
    def __init__(self):
        super(Model, self).__init__()

        self.lstm_0_0 = nn.LSTM(input_size=32, hidden_size=16)
        self.lstm_0_1 = nn.LSTM(input_size=16, hidden_size=16, num_layers=3, bias=False)
        self.lstm_0_2 = nn.LSTM(input_size=16, hidden_size=16, num_layers=4, bias=True, bidirectional=True, proj_size=10)
        self.lstm_0_3 = nn.LSTM(input_size=20, hidden_size=16, num_layers=4, bias=True, bidirectional=True, proj_size=10)
        self.lstm_0_4 = nn.LSTM(input_size=20, hidden_size=16, num_layers=4, bias=True, bidirectional=True, proj_size=10)

        self.lstm_1_0 = nn.LSTM(input_size=25, hidden_size=16, batch_first=True)
        self.lstm_1_1 = nn.LSTM(input_size=16, hidden_size=16, num_layers=3, bias=False, batch_first=True)
        self.lstm_1_2 = nn.LSTM(input_size=16, hidden_size=16, num_layers=4, bias=True, batch_first=True, bidirectional=True, proj_size=10)
        self.lstm_1_3 = nn.LSTM(input_size=20, hidden_size=16, num_layers=4, bias=True, batch_first=True, bidirectional=True, proj_size=10)
        self.lstm_1_4 = nn.LSTM(input_size=20, hidden_size=16, num_layers=4, bias=True, batch_first=True, bidirectional=True, proj_size=10)

    def forward(self, x, y):
        x = x.permute(1, 0, 2)

        x0, _ = self.lstm_0_0(x)
        x1, _ = self.lstm_0_1(x0)
        x2, (h0, c0) = self.lstm_0_2(x1)
        x3, (h1, c1) = self.lstm_0_3(x2, (h0, c0))
        x4, _ = self.lstm_0_4(x3, (h1, c1))

        y0, _ = self.lstm_1_0(y)
        y1, _ = self.lstm_1_1(y0)
        y2, (h2, c2) = self.lstm_1_2(y1)
        y3, (h3, c3) = self.lstm_1_3(y2, (h2, c2))
        y4, _ = self.lstm_1_4(y3, (h3, c3))

        x2 = x2.permute(1, 0, 2)
        x3 = x3.permute(1, 0, 2)
        x4 = x4.permute(1, 0, 2)

        return x2, x3, x4, y2, y3, y4

def test():
    net = Model().half().float()
    net.eval()

    torch.manual_seed(0)
    x = torch.rand(1, 10, 32)
    y = torch.rand(1, 12, 25)

    a = net(x, y)

    # export torchscript
    mod = torch.jit.trace(net, (x, y))
    mod.save("test_nn_LSTM.pt")

    # torchscript to pnnx
    import os
    os.system("../../src/pnnx test_nn_LSTM.pt inputshape=[1,10,32],[1,12,25]")

    # ncnn inference
    import test_nn_LSTM_ncnn
    b = test_nn_LSTM_ncnn.test_inference()

    for a0, b0 in zip(a, b):
        if not torch.allclose(a0, b0, 1e-3, 1e-3):
            return False
    return True

if __name__ == "__main__":
    if test():
        exit(0)
    else:
        exit(1)
