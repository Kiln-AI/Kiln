from probe import run, TOOLS
run("V openai/gpt-5.5 minimal (map says unsupported) chat path", model="openai/gpt-5.5", reasoning_effort="minimal")
run("W openai/responses/gpt-5.5 minimal bridge path", model="openai/responses/gpt-5.5", reasoning_effort="minimal")
run("X openai/responses/gpt-5 xhigh bridge path", model="openai/responses/gpt-5", reasoning_effort="xhigh")
run("Y openai/gpt-5 none chat path", model="openai/gpt-5", reasoning_effort="none")
run("Z openai/gpt-5.5-pro low (auto bridged, map says low unsupported)", model="openai/gpt-5.5-pro", reasoning_effort="low")
