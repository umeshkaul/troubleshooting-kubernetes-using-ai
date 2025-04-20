# Using AI to Troubleshoot Kubernetes Clusters

## Summary

Artificial intelligence continues to transform our lives. This post explores how we can use it to help us troubleshoot problems in a Kubernetes cluster.

#### AI Needs Access to Your Cluster

First of all, if you ask ChatGPT questions about Kubernetes, it surely knows about it. But in order for it to help you troubleshoot issues in a Kubernetes cluster, it must have control over it.

Basically, an LLM (Large Language Model) should be able to mimic what a typical Kubernetes administrator would do—i.e., run commands, look at the output, and then decide the next step until the problem is solved.

#### Tools/Function Calling

This is exactly what the **function/tool calling** feature is designed to address. You can read more about it [here](https://platform.openai.com/docs/guides/function-calling?api-mode=chat#overview). This feature is used by AI agents to accomplish complex, multi-step operations e.g

Example interaction with an AI-Agent with access to run commands against your cluster:  

> You say:  
> “A pod in my Kubernetes cluster isn’t starting.”  
>   
> The AI agent uses function calling to run:  
> `kubectl get pods -A`  
>   
> It sees the pod status is `ErrImagePull`, then runs:  
> `kubectl describe pod`  
>   
> It finds the reason:  
> `"Failed to pull image 'myregistry/payments-api:latest' – image not found."`  
>   
> It replies:  
> *“The pod can’t start because the image `myregistry/payments-api:latest` doesn’t exist or is inaccessible—check the image name or your registry credentials.”*  
>   
> The AI agent can now also **fix the problem** if you ask it to.

In this post, we will use function/tool calling with below tools to troubleshoot three problem scenarios listed below in a local [kind](https://kind.sigs.k8s.io/) cluster:

- `gptscript` – for OpenAI's function calling  
- `k8sgpt` – for scanning problems within a Kubernetes cluster  
- `kubectl` – for interacting with the cluster

#### Problem Scenarios 

- mis-configured nginx image tag : In this scenario we will apply [this deployment](./misconfigured-nginx-image-scenario/misconfigured-nginx-image.yaml) which has wrong label resulting in pod not being able to start.
- mis-configured root volume for nginx: In this scenario we will apply [this deployment](./misconfigured-nginx-ro-volume-scenario/misconfigured-nginx-ro-root-volume.yaml) which has a nginx deployment but with mis-configured root volume resulting in pod not being able to start.
- mis-configured service label: In this scenario we will apply [this deployment](./misconfigured-nginx-service-label/misconfigured-label.yaml) which has a nginx deployment but with mis-configured service label. This results in service having no endpoints.

#### System Overview

Below is a schematic that shows the **data flow between different components** of the system we will use to troubleshoot.
 
```
+--------+           +-----------+           +--------+
|  User  +---------> | gptscript +<--------->|  LLM   |
+--------+           +-----------+           +--------+
                          |
                          | executes 
                          | commands on 
                          | local machine
                          v
                +----------------------+
                |   kubectl / k8sgpt   |
                +----------------------+

```
Flow Description:   
1. The user provides a natural language instruction to `gptscript` cli tool asking it to solve the problem. As part of instructions LLM is also told that it has access to run `kubectl` and `k8sgpt` commands if needed. Note that LLM cannot run these commands directly on your computer but ask `gptscript` to run them and report the results(using function/tools calling feature of OpenAI).
2. `gptscript` (runs on user's system) sends that input to the LLM using function/tool calling.
3. The LLM returns structured instructions (e.g., "run kubectl get pods").
4. `gptscript` executes those commands (like `kubectl` or `k8sgpt`) in the terminal (runs on user's system).
5. Results can optionally be sent back to the LLM for follow-up actions.  

>**NOTE**: *If you’ve been following the AI space, you may have heard of [Anthropic’s MCP](https://www.anthropic.com/news/model-context-protocol) (Multi-Agent Collaboration Protocol) and the broader concept of AI agents. While we won’t be using MCP specifically, the core idea is the same: leveraging the tool-calling capabilities of large language models (LLMs) to solve complex problems through intelligent, multi-step reasoning. Anthropic’s MCP is a protocol that standardizes how AI, tools, and agents communicate, making it easier for them to work together. For example, if an AI agent needs to diagnose a server issue, it can use MCP to ask a monitoring tool for logs, analyze them using a language model, and respond with a clear solution—all in a smooth, coordinated flow.* 
*`k8sGpt` is also working on adding [MCP support](https://k8sgpt.ai/roadmap) which when available will remove the need for `gptscript` in our example below*

Feel free to clone this repo and try it out yourself. 

One thing which will become very clear from the observations below is that LLM's by design are inherently non-determentitic which means clear and **precise prompts** are critical to getting desired result, especially when specifying what **NOT** to do, like avoiding changes to some security policies in your manifests (see example below). To gain a better insight into LLM behavior specifically in the context of troubleshooting Kubernetes issues, I recommend walking through the examples below especially [Troubleshooting mis-configured root volume](#troubleshooting-mis-configured-root-volume). 

Before diving into the scenarios, let’s briefly review the CLI tools we’ll be using. 


## Introduction to Tools 

### K8sGPT : AI-Powered Kubernetes Troubleshooting

[K8sGPT](https://k8sgpt.ai) is an AI-powered tool designed to scan your Kubernetes clusters and identify issues, translating them into easy-to-understand explanations. It operates in two distinct modes: Analyze and Explain.

In **Analyze mode**, K8sGPT uses its built-in rules engine to detect common problems within the cluster. This mode provides a straightforward diagnostic based on predefined patterns.

In **Explain mode**, it takes the output from Analyze mode and passes it through a large language model (LLM) to generate human-friendly explanations and actionable guidance.

<details>
 <summary>Here are some examples to demonstrate how each mode works in practice</summary>

#### Analyze Mode 

```
#  `k8sgpt analyze` command run against a cluster and the output of this command is the list of issues found with the (no AI is used) 

$k8sgpt analyze
AI Provider: AI not used; --explain not set

0: Service default/nginx()
- Error: Service has not ready endpoints, pods: [Pod/nginx-7d7598dfdb-rlp9d], expected 1

1: Pod default/nginx-7d7598dfdb-rlp9d(Deployment/nginx)
- Error: Back-off pulling image "nginx007"
```

#### Explain Mode

This is where AI is used. In this mode, the output from the `Analyze mode` (above) is provided to AI so that AI can transform the list of problems identified in the Analyze mode to output more user friendly instructions to fix the problem. 

 ```
 # Here the output of 'k8sgpt analyze' command with '--explain' option is fed to AI which returns human friendly instructions on how to go about fixing the issue. 

$k8sgpt analyze --explain
 100% |███████████████████████████████████████████████████████████████████████████████████████████████████████████| (2/2, 9957 it/s)
AI Provider: openai

0: Service default/nginx()
- Error: Service has not ready endpoints, pods: [Pod/nginx-7d7598dfdb-rlp9d], expected 1
Error: The service cannot route traffic because it has no available endpoints; the expected pod is not ready.

Solution:
1. Check pod status: `kubectl get pods`
2. Describe the pod: `kubectl describe pod nginx-7d7598dfdb-rlp9d`
3. Look for errors in events or logs: `kubectl logs nginx-7d7598dfdb-rlp9d`
4. Ensure readiness probes are configured correctly.
5. Fix any issues and redeploy if necessary.
1: Pod default/nginx-7d7598dfdb-rlp9d(Deployment/nginx)
- Error: Back-off pulling image "nginx007"
Error: The Kubernetes cluster is unable to pull the Docker image "nginx007" from the specified registry, likely due to it not being found or authentication issues.

Solution:
1. Check if the image name is correct.
2. Verify the image exists in the registry.
3. Ensure proper access credentials are set up.
4. If using a private registry, configure imagePullSecrets.
5. Retry deploying the pod.
```

</details>

### GPTScript: Natural Language Task Automation (Automating LLM Interactions)

[GPTScript](https://github.com/gptscript-ai/gptscript) is a scripting language designed to automate interactions with Large Language Models (LLMs). It enables users to combine natural language prompts with traditional scripting elements like Bash, Python, and more. At its core, GPTScript leverages the function/tool-calling capabilities of LLMs to perform local tasks. This same mechanism is also used by AI agents to accomplish more complex, multi-step operations. You can read more about it [here](https://platform.openai.com/docs/guides/function-calling?api-mode=chat#overview). Here is an [example](./python-function-calling-example/test-openai-function.py) of how to use this feature in python.

Typically, an AI model doesn’t have direct access to your local system or data. For example, if you ask an LLM to find the largest file on your computer, it won't be able to perform the task—unless you explicitly allow it to interact with your machine through commands.

GPTScript solves this by giving the LLM structured access to your environment. You define which commands or tools it can use, and GPTScript acts as a bridge between your system and the AI. You can think of these instructions same as the prompt you provide to chatgpt just a set of instructions in plain english. 

<details>
 <summary>Here is an example of how to have LLM answer question “What is the largest file in this directory?” </summary>

In the example below, we enable the LLM to run the ls command on the local system. With that access, it can then analyze the output and answer a question like:

> “What is the largest file in this directory?”

This kind of interaction is powerful, as it combines the reasoning ability of LLMs with the execution capabilities of traditional scripts—all while keeping the user in control of what the AI can access.

##### Step-1:  Put instructions you want LLM to follow in a text file 
    
    - The `tools:sys.exec?` below is needed to allow gptscript access to run commands on your system e.g `ls` etc  
    - The `description` below is instructing LLM on what role we want it to play  

    ```
    $ cat list-files.gpt
    tools: sys.exec?
    description: A linux system admin

    You are a linux system admin with 'ls' command line tool available to you.
    List the files in the current directory and give me the name of the largest file only
    ```

    ##### Step-2: Run the gptscript cli tool and provide it above file as an argument. The instructions in this file are sent to AI and the output from that is displayed to the user. 
    ```
    $ gptscript list-files.gpt
    12:03:51 started  [main]
    12:03:51 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"ls -lS | head -n 2 | tail -n 1 | awk '{print $9}'"}
    12:03:53 started  [sys.exec(2)] [input={"command":"ls -lS | head -n 2 | tail -n 1 | awk '{print $9}'"}]
    12:03:53 sent     [sys.exec(2)]
            content  [2] content | gptscript-v0.9.2-linux-amd64.tar.gz
            content  [2] content |
    12:03:53 ended    [sys.exec(2)] [output=gptscript-v0.9.2-linux-amd64.tar.gz]
    12:03:53 continue [main]
    12:03:53 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | gptscript-v0.9.2-linux-amd64.tar.gz
    12:03:54 ended    [main] [output=gptscript-v0.9.2-linux-amd64.tar.gz]
    12:03:54 usage    [total=501] [prompt=450] [completion=51]

    OUTPUT:
    gptscript-v0.9.2-linux-amd64.tar.gz
    ```
</details>

## Troubleshooting Scenarios 
We will create a kind cluster and then introduce three different types of problems in it and then use the combination of `k8sgpt` and `gptscript` tool to troubleshoot and fix the issue. 

### Create a kind cluster

<details>
 <summary>Command to create a single node kind cluster </summary>

    ```
    $kind create cluster --name ai-troubleshooting
    Creating cluster "ai-troubleshooting" ...
    ✓ Ensuring node image (kindest/node:v1.32.2) 🖼
    ✓ Preparing nodes 📦
    ✓ Writing configuration 📜
    ✓ Starting control-plane 🕹️
    ✓ Installing CNI 🔌
    ✓ Installing StorageClass 💾
    Set kubectl context to "kind-ai-troubleshooting"
    You can now use your cluster with:

    kubectl cluster-info --context kind-ai-troubleshooting

    Thanks for using kind! 😊
    ```
</details>

### OpenAI Configuration for `k8sgpt` and `gptscript`
We will be using OpenAI so you need to get your [OpenAI API key](https://platform.openai.com/api-keys) and configure it as below. The commands we use below will be needing this configuration.

<details>
 <summary>OpenAI Configuration for k8sgpt </summary>

- Create a file named `k8sgpt.yaml` and put your API key. We will use this file as an argument later to the k8sgpt command 

    ```
    $cat k8sgpt.yaml
    ai:
        providers:
        - name: openai
        model: gpt-4o-mini      # you can use any model but I found gpt-4o-mini to be ok for my testing
        password: XXXXXXXXXXXX  # your OpenAI API key goes here
        temperature: 0.7
        topp: 0.5
        topk: 50
        maxtokens: 2048
        defaultprovider: "openai"
    ```

</details>

<details>
 <summary>OpenAI Configuration for gptscript </summary>

    ```
    $cat openai.env
    export OPENAI_API_KEY=your-OpenAI-API-key-goes-here

    $source ./openai.env
    ```
</details>


### SCENARIO-1: Troubleshooting mis-configured image issue

In this scenario we will apply [this deployment](./misconfigured-nginx-image-scenario/misconfigured-nginx-image.yaml) which has a mis-configured nginx image tag and then try to use `k8sgpt` tool to diagnose the issue and `gptscript` to fix the issue. This is a vey simple problem and based on my testing AI always fixed it. I cannot say samething about the more complex scenarios. The most important thing I learnt is that the instructions/prompt you provide to AI have to be very precise e.g if you do not tell AI specifically not to fix an issue, it may just fix it. 

<details>
 <summary>Step by Step Process </summary>

1. Apply the manifest 

    ```
    $k apply -f misconfigured-nginx-image-scenario/misconfigured-nginx-image.yaml
    deployment.apps/nginx created
    service/nginx created
    ```
2. Run `kubectl` command to see that there is a problem. Our goal is to use AI to fix this problem. 
    ```
    $k get pods,svc
    NAME                         READY   STATUS         RESTARTS   AGE
    pod/nginx-5545cbc86d-2j6nh   0/1     ErrImagePull   0          3s

    NAME                 TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)   AGE
    service/kubernetes   ClusterIP   10.96.0.1      <none>        443/TCP   58m
    service/nginx        ClusterIP   10.96.177.16   <none>        80/TCP    3s
    ```
3. Use `k8sgpt` command with the `k8sgpt.yaml` we setup previously to see the problem (we get detailed instructions on how to fix the probelm)

    ```
    $k8sgpt analyze -c k8sgpt.yaml --explain
    100% |██████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| (2/2, 15 it/min)
    AI Provider: openai

    0: Service default/nginx()
    - Error: Service has not ready endpoints, pods: [Pod/nginx-5545cbc86d-2j6nh], expected 1
    Error: The service cannot route traffic because it has no available endpoints; the expected pod is not ready.

    Solution:
    1. Check pod status: `kubectl get pods`
    2. Describe the pod: `kubectl describe pod nginx-5545cbc86d-2j6nh`
    3. Look for errors in events or logs: `kubectl logs nginx-5545cbc86d-2j6nh`
    4. Ensure readiness probes are configured correctly.
    5. If issues persist, redeploy the pod or check resource limits.
    1: Pod default/nginx-5545cbc86d-2j6nh(Deployment/nginx)
    - Error: Back-off pulling image "nginx007": ErrImagePull: failed to pull and unpack image "docker.io/library/nginx007:latest": failed to resolve reference "docker.io/library/nginx007:latest": pull access denied, repository does not exist or may require authorization: server message: insufficient_scope: authorization failed
    Error: The error indicates that Kubernetes cannot pull the image "nginx007" from Docker Hub due to access issues, possibly because the image doesn't exist or requires authentication.

    Solution:
    1. Verify the image name is correct.
    2. Check if the image exists on Docker Hub.
    3. If private, log in using `docker login`.
    4. Update Kubernetes deployment with correct image or credentials.
    5. Redeploy the application.
    ```
    - we still have the problem
    ```
    $k get pods,svc
    NAME                         READY   STATUS             RESTARTS   AGE
    pod/nginx-5545cbc86d-2j6nh   0/1     ImagePullBackOff   0          47s

    NAME                 TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)   AGE
    service/kubernetes   ClusterIP   10.96.0.1      <none>        443/TCP   59m
    service/nginx        ClusterIP   10.96.177.16   <none>        80/TCP    47s
    ```

4. We now need to build a text file which has instructions which `gptscript` can provide to AI and help us diagnose the use (we will fix it in the next step). These are simple natural language instructions (similar to prompts we provide to chatgpt). 

    The `tools:sys.exec?` below is needed to allow gptscript access to run commands on your system e.g `ls` etc
    The `description` below is instructing LLM on what role we want it to play

    ```bash
    $cat gptscript-instructions/k8sgpt-diag.gpt
    tools: sys.exec?
    description: A kubernetes system admin

    Do the following sequentially, do not run in parallel

    1. You are a kubernetes system admin with "kubectl" command available to you
    2. You can also use "k8sgpt analyze" command to detect any problems with the cluster
    3. Do not make any changes to the cluster.
    4. Please provide detailed instructions on how to fix the problems you find

    ```
5. DIAGNOSE the issue (do not fix yet) using  `gptscript --default-model=gpt-4o-mini  gptscript-instructions/k8sgpt-diag.gpt` command with above instructions 

    ```bash
    $gptscript --default-model=gpt-4o-mini gptscript-instructions/k8sgpt-diag.gpt
    11:26:54 WARNING: Changing the default model can have unknown behavior for existing tools. Use the model field per tool instead.
    11:26:54 started  [main]
    11:26:54 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"k8sgpt analyze"}
    11:26:54 started  [sys.exec(2)] [input={"command":"k8sgpt analyze"}]
    11:26:54 sent     [sys.exec(2)]
            content  [2] content | AI Provider: AI not used; --explain not set
            content  [2] content |
            content  [2] content | 0: Service default/nginx()
            content  [2] content | - Error: Service has not ready endpoints, pods: [Pod/nginx-5545cbc86d-2j6nh], expected 1
            content  [2] content |
            content  [2] content | 1: Pod default/nginx-5545cbc86d-2j6nh(Deployment/nginx)
            content  [2] content | - Error: failed to pull and unpack image "docker.io/library/nginx007:latest": failed to resolve refe ...
            content  [2] content |
            content  [2] content |
            content  [2] content |
    11:26:55 ended    [sys.exec(2)] [output=AI Provider: AI not used; --explain not set\n\n0: Service default/nginx()\n- Error: Service has not rea...]
    11:26:55 continue [main]
    11:26:55 sent     [main]
            content  [1] content | Waiting for model response...         content  [1] content | ### Problems Detected:
            content  [1] content |
            content  [1] content | 1. **Service Issue**: The service `default/nginx` has not ready endpoints. The pod `nginx-5545cbc86d-2j6nh` is expected to be ready but is not.
            content  [1] content |
            content  [1] content | 2. **Pod Issue**: The pod `default/nginx-5545cbc86d-2j6nh` (part of the deployment `nginx`) failed to pull and unpack the image `docker.io/library/nginx007:latest`. The error indicates that the image may not exist or requires authorization.
            content  [1] content |
            content  [1] content | ### Instructions to Fix the Problems:
            content  [1] content |
            content  [1] content | 1. **For the Service Issue**:
            content  [1] content |    - Check the status of the pod using the command:
            content  [1] content |      ```bash
            content  [1] content |      kubectl get pods -n default
            content  [1] content |      ```
            content  [1] content |    - Investigate the logs of the pod to understand why it is not ready:
            content  [1] content |      ```bash
            content  [1] content |      kubectl logs nginx-5545cbc86d-2j6nh -n default
            content  [1] content |      ```
            content  [1] content |    - Ensure that the pod is correctly configured and that any dependencies it requires are available.
            content  [1] content |
            content  [1] content | 2. **For the Pod Issue**:
            content  [1] content |    - Verify the image name in your deployment configuration. It seems that `nginx007:latest` may not be a valid image. You can check the available images in Docker Hub or your private registry.
            content  [1] content |    - If the image is incorrect, update the deployment to use a valid image, such as:
            content  [1] content |      ```yaml
            content  [1] content |      image: nginx:latest
            content  [1] content |      ```
            content  [1] content |    - If the image is correct but requires authentication, ensure that you have the necessary image pull secrets configured in your Kubernetes cluster. You can create a secret using:
            content  [1] content |      ```bash
            content  [1] content |      kubectl create secret docker-registry myregistrykey --docker-server=<DOCKER_SERVER> --docker-username=<DOCKER_USERNAME> --docker-password=<DOCKER_PASSWORD> --docker-email=<DOCKER_EMAIL>
            content  [1] content |      ```
            content  [1] content |    - Then, link the secret to your service account or specify it in your deployment configuration.
            content  [1] content |
            content  [1] content | 3. **Redeploy the Application**:
            content  [1] content |    - After making the necessary changes, redeploy the application using:
            content  [1] content |      ```bash
            content  [1] content |      kubectl apply -f <your-deployment-file>.yaml
            content  [1] content |      ```
            content  [1] content |
            content  [1] content | 4. **Monitor the Status**:
            content  [1] content |    - Continuously monitor the status of the pods and services to ensure they are running correctly:
            content  [1] content |      ```bash
            content  [1] content |      kubectl get pods -n default
            content  [1] content |      kubectl get services -n default
            content  [1] content |      ```
    11:27:03 ended    [main] [output=### Problems Detected:\n\n1. **Service Issue**: The service `default/nginx` has not ready endpoints. T...]
    11:27:03 usage    [total=1153] [prompt=634] [completion=519]

    OUTPUT:

    ### Problems Detected:

    1. **Service Issue**: The service `default/nginx` has not ready endpoints. The pod `nginx-5545cbc86d-2j6nh` is expected to be ready but is not.

    2. **Pod Issue**: The pod `default/nginx-5545cbc86d-2j6nh` (part of the deployment `nginx`) failed to pull and unpack the image `docker.io/library/nginx007:latest`. The error indicates that the image may not exist or requires authorization.

    ### Instructions to Fix the Problems:

    1. **For the Service Issue**:
    - Check the status of the pod using the command:
        ```bash
        kubectl get pods -n default
        ```
    - Investigate the logs of the pod to understand why it is not ready:
        ```bash
        kubectl logs nginx-5545cbc86d-2j6nh -n default
        ```
    - Ensure that the pod is correctly configured and that any dependencies it requires are available.

    2. **For the Pod Issue**:
    - Verify the image name in your deployment configuration. It seems that `nginx007:latest` may not be a valid image. You can check the available images in Docker Hub or your private registry.
    - If the image is incorrect, update the deployment to use a valid image, such as:
        ```yaml
        image: nginx:latest
        ```
    - If the image is correct but requires authentication, ensure that you have the necessary image pull secrets configured in your Kubernetes cluster. You can create a secret using:
        ```bash
        kubectl create secret docker-registry myregistrykey --docker-server=<DOCKER_SERVER> --docker-username=<DOCKER_USERNAME> --docker-password=<DOCKER_PASSWORD> --docker-email=<DOCKER_EMAIL>
        ```
    - Then, link the secret to your service account or specify it in your deployment configuration.

    3. **Redeploy the Application**:
    - After making the necessary changes, redeploy the application using:
        ```bash
        kubectl apply -f <your-deployment-file>.yaml
        ```

    4. **Monitor the Status**:
    - Continuously monitor the status of the pods and services to ensure they are running correctly:
        ```bash
        kubectl get pods -n default
        kubectl get services -n default
        ```
    ```
- we still have the issue and will fix it in the next step

    ```bash
    $k get pods,svc
    NAME                         READY   STATUS             RESTARTS   AGE
    pod/nginx-5545cbc86d-2j6nh   0/1     ImagePullBackOff   0          2m2s

    NAME                 TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)   AGE
    service/kubernetes   ClusterIP   10.96.0.1      <none>        443/TCP   60m
    service/nginx        ClusterIP   10.96.177.16   <none>        80/TCP    2m2s
    ```

5. FIX the issue using `gptscript` with below modified instructions

- gptscript instructions

    ```bash
    $cat gptscript-instructions/k8sgpt-diag-fix.gpt
    tools: sys.exec?
    description: A kubernetes system admin

    Do the following sequentially, do not run in parallel

    1. You are a kubernetes system admin with kubectl command available to you
    2. Use "k8sgpt analyze" command to check if there are any problems with the cluster or pods running.
    3. Use "kubectl" command to check if there are any issues. Check pod logs to see if there are any issues.
    4. Do not use "kubectl edit" command to make changes.
    5. Only use "kubectl patch" command to make changes.
    6. Wait for 15 seconds to verify that the changes you made fixed the problem
    7. Provide details on steps you took to fix the problem
    ```

- run gptscript command with above instructions

    ```bash
    $gptscript --default-model=gpt-4o-mini gptscript-instructions/k8sgpt-diag-fix.gpt
    11:29:54 WARNING: Changing the default model can have unknown behavior for existing tools. Use the model field per tool instead.
    11:29:54 started  [main]
    11:29:54 sent     [main]
    11:29:54 started  [sys.exec(2)] [input={"command":"k8sgpt analyze"}]
    11:29:54 sent     [sys.exec(2)]
            content  [2] content | AI Provider: AI not used; --explain not set
            content  [2] content |
            content  [2] content | 0: Service default/nginx()
            content  [2] content | - Error: Service has not ready endpoints, pods: [Pod/nginx-5545cbc86d-2j6nh], expected 1
            content  [2] content |
            content  [2] content | 1: Pod default/nginx-5545cbc86d-2j6nh(Deployment/nginx)
            content  [2] content | - Error: Back-off pulling image "nginx007": ErrImagePull: failed to pull and unpack image "docker.io ...
            content  [2] content |
            content  [2] content |
            content  [2] content |
    11:29:54 ended    [sys.exec(2)] [output=AI Provider: AI not used; --explain not set\n\n0: Service default/nginx()\n- Error: Service has not rea...]
    11:29:54 continue [main]
    11:29:54 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pods"}
    11:29:55 started  [sys.exec(3)] [input={"command":"kubectl get pods"}]
    11:29:55 sent     [sys.exec(3)]
            content  [3] content | NAME                     READY   STATUS             RESTARTS   AGE
            content  [3] content | nginx-5545cbc86d-2j6nh   0/1     ImagePullBackOff   0          4m46s
            content  [3] content |
    11:29:55 ended    [sys.exec(3)] [output=NAME                     READY   STATUS             RESTARTS   AGE\nnginx-5545cbc86d-2j6nh   0/1...]
    11:29:55 continue [main]
    11:29:55 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl logs nginx-5545cbc86d-2j6nh"}
    11:29:55 started  [sys.exec(4)] [input={"command":"kubectl logs nginx-5545cbc86d-2j6nh"}]
    11:29:55 sent     [sys.exec(4)]
            content  [4] content | Error from server (BadRequest): container "nginx" in pod "nginx-5545cbc86d-2j6nh" is waiting to star ...
            content  [4] content |
    11:29:56 ended    [sys.exec(4)] [output=ERROR: exit status 1\nOUTPUT:\nError from server (BadRequest): container \"nginx\" in pod \"nginx-5545cbc...]
    11:29:56 continue [main]
    11:29:56 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl patch deployment nginx -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"image\":\"nginx:latest\"}]} }}}}'"}
    11:29:57 started  [sys.exec(5)] [input={"command":"kubectl patch deployment nginx -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"image\":\"nginx:latest\"}]} }}}}'"}]
    11:29:57 sent     [sys.exec(5)]
            content  [5] content | Error from server (BadRequest): invalid character '}' after top-level value
            content  [5] content |
    11:29:57 ended    [sys.exec(5)] [output=ERROR: exit status 1\nOUTPUT:\nError from server (BadRequest): invalid character '}' after top-level v...]
    11:29:57 continue [main]
    11:29:57 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl patch deployment nginx -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"image\":\"nginx:latest\"}]} }}}'"}
    11:29:58 started  [sys.exec(6)] [input={"command":"kubectl patch deployment nginx -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"image\":\"nginx:latest\"}]} }}}'"}]
    11:29:58 sent     [sys.exec(6)]
            content  [6] content | deployment.apps/nginx patched
            content  [6] content |
    11:29:58 ended    [sys.exec(6)] [output=deployment.apps/nginx patched]
    11:29:58 continue [main]
    11:29:58 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"sleep 15"}
    11:29:58 started  [sys.exec(7)] [input={"command":"sleep 15"}]
    11:29:58 sent     [sys.exec(7)]
    11:30:13 ended    [sys.exec(7)]
    11:30:13 continue [main]
    11:30:13 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pods"}
    11:30:14 started  [sys.exec(8)] [input={"command":"kubectl get pods"}]
    11:30:14 sent     [sys.exec(8)]
            content  [8] content | NAME                     READY   STATUS    RESTARTS   AGE
            content  [8] content | nginx-54c98b4f84-62vg2   1/1     Running   0          16s
            content  [8] content |
    11:30:14 ended    [sys.exec(8)] [output=NAME                     READY   STATUS    RESTARTS   AGE\nnginx-54c98b4f84-62vg2   1/1     Running...]
    11:30:14 continue [main]
    11:30:14 sent     [main]
            content  [1] content | Waiting for model response...         content  [1] content | I fixed the problem with the Kubernetes cluster by following these steps:
            content  [1] content |
            content  [1] content | 1. Analyzed the cluster using the command `k8sgpt analyze`, which revealed that the pod `nginx-5545cbc86d-2j6nh` was in an `ImagePullBackOff` state due to an error pulling the image `nginx007`.
            content  [1] content | 2. Checked the pod status with `kubectl get pods`, confirming the `ImagePullBackOff` status.
            content  [1] content | 3. Attempted to retrieve the pod logs using `kubectl logs`, but it failed because the container was waiting to start.
            content  [1] content | 4. Used the `kubectl patch` command to update the deployment to use the correct image `nginx:latest` instead of the non-existent `nginx007`.
            content  [1] content | 5. Waited for 15 seconds to allow the changes to take effect.
            content  [1] content | 6. Verified the pod status again with `kubectl get pods`, and confirmed that the pod is now `Running`.
    11:30:17 ended    [main] [output=I fixed the problem with the Kubernetes cluster by following these steps:\n\n1. Analyzed the cluster u...]
    11:30:17 usage    [total=5088] [prompt=4715] [completion=373]

    OUTPUT:

    I fixed the problem with the Kubernetes cluster by following these steps:

    1. Analyzed the cluster using the command `k8sgpt analyze`, which revealed that the pod `nginx-5545cbc86d-2j6nh` was in an `ImagePullBackOff` state due to an error pulling the image `nginx007`.
    2. Checked the pod status with `kubectl get pods`, confirming the `ImagePullBackOff` status.
    3. Attempted to retrieve the pod logs using `kubectl logs`, but it failed because the container was waiting to start.
    4. Used the `kubectl patch` command to update the deployment to use the correct image `nginx:latest` instead of the non-existent `nginx007`.
    5. Waited for 15 seconds to allow the changes to take effect.
    6. Verified the pod status again with `kubectl get pods`, and confirmed that the pod is now `Running`.
    ```
- VERIFY that the issue is fixed

    ```bash
    $k get pods,svc
    NAME                         READY   STATUS    RESTARTS   AGE
    pod/nginx-54c98b4f84-62vg2   1/1     Running   0          77s

    NAME                 TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)   AGE
    service/kubernetes   ClusterIP   10.96.0.1      <none>        443/TCP   64m
    service/nginx        ClusterIP   10.96.177.16   <none>        80/TCP    6m6s
    ```
</details>

### SCENARIO-2: Troubleshooting mis-configured root volume 
In this scenario we will apply [this deployment](./misconfigured-nginx-ro-volume-scenario/misconfigured-nginx-ro-root-volume.yaml) which has a nginx deployment but with mis-configured root volume. I have also provided a [working copy of this manifest](./misconfigured-nginx-ro-volume-scenario/working-nginx-ro-root-volume.yaml) to give an idea of what AI needs to do to fix this issue. As you can see this is much more complex scenario and I have had mixed luck with this. Sometimes AI went into a loop, sometimes it just deleted the deployment and did not know what to do next and sometimes it did fix it. 

Again the most important thing I learnt is that the instructions/prompt you provide to AI has to be very precise e.g if you do not tell AI specifically not to fix an issue, it may just fix it. 

#### First Attempt

Trying to fix the problem using an older OpenAI model `gpt-4o-mini` FAILED.  

<details>
 <summary>Step by Step Process </summary>

1. Make sure we start clean and then Apply the manifest to create the problem

    ```bash
    $k get pods,svc
    NAME                 TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)   AGE
    service/kubernetes   ClusterIP   10.96.0.1    <none>        443/TCP   81m
    
    $k8sgpt analyze
    AI Provider: AI not used; --explain not set

    No problems detected
    ```

    ```bash
    $k apply -f misconfigured-nginx-ro-volume-scenario/misconfigured-nginx-ro-root-volume.yaml
    deployment.apps/nginx-ro-root created
    $
    $k get pods
    NAME                             READY   STATUS              RESTARTS   AGE
    nginx-ro-root-65f7f86764-wr675   0/1     ContainerCreating   0          3s
    $
    $k get pods
    NAME                             READY   STATUS   RESTARTS     AGE
    nginx-ro-root-65f7f86764-wr675   0/1     Error    1 (3s ago)   6s
    $
    $k8sgpt analyze
    AI Provider: AI not used; --explain not set

    0: Pod default/nginx-ro-root-65f7f86764-wr675(Deployment/nginx-ro-root)
    - Error: the last termination reason is Error container=nginx pod=nginx-ro-root-65f7f86764-wr675
    
    $k logs nginx-ro-root-65f7f86764-wr675
    /docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration
    /docker-entrypoint.sh: Looking for shell scripts in /docker-entrypoint.d/
    /docker-entrypoint.sh: Launching /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
    10-listen-on-ipv6-by-default.sh: info: can not modify /etc/nginx/conf.d/default.conf (read-only file system?)
    /docker-entrypoint.sh: Sourcing /docker-entrypoint.d/15-local-resolvers.envsh
    /docker-entrypoint.sh: Launching /docker-entrypoint.d/20-envsubst-on-templates.sh
    /docker-entrypoint.sh: Launching /docker-entrypoint.d/30-tune-worker-processes.sh
    /docker-entrypoint.sh: Configuration complete; ready for start up
    2025/04/18 15:53:20 [emerg] 1#1: mkdir() "/var/cache/nginx/client_temp" failed (30: Read-only file system)
    nginx: [emerg] mkdir() "/var/cache/nginx/client_temp" failed (30: Read-only file system)
    ```

2. Use the below instructions for `gptscript` 

    ```bash
    $cat gptscript-instructions/k8sgpt-diag-fix.gpt
    tools: sys.exec?
    description: A kubernetes system admin

    Do the following sequentially, do not run in parallel

    1. You are a kubernetes system admin with kubectl command available to you
    2. Use "k8sgpt analyze" command to check if there are any problems with the cluster or pods running.
    3. Use "kubectl" command to check if there are any issues. Check pod logs to see if there are any issues.
    4. Do not use "kubectl edit" command to make changes.
    5. Only use "kubectl patch" command to make changes.
    6. Wait for 15 seconds to verify that the changes you made fixed the problem
    7. Provide details on steps you took to fix the problem
    ```

3. Trying to fix the problem using `gpt-4o-mini` FAILS

    ```bash
    $gptscript --default-model=gpt-4o-mini gptscript-instructions/k8sgpt-diag-fix.gpt
    11:55:17 WARNING: Changing the default model can have unknown behavior for existing tools. Use the model field per tool instead.
    11:55:17 started  [main]
    11:55:17 sent     [main]
    11:55:17 started  [sys.exec(2)] [input={"command":"k8sgpt analyze"}]
    11:55:17 sent     [sys.exec(2)]
            content  [2] content | AI Provider: AI not used; --explain not set
            content  [2] content |
            content  [2] content | 0: Pod default/nginx-ro-root-65f7f86764-wr675(Deployment/nginx-ro-root)
            content  [2] content | - Error: the last termination reason is Error container=nginx pod=nginx-ro-root-65f7f86764-wr675
            content  [2] content |
            content  [2] content |
            content  [2] content |
    11:55:17 ended    [sys.exec(2)] [output=AI Provider: AI not used; --explain not set\n\n0: Pod default/nginx-ro-root-65f7f86764-wr675(Deploymen...]
    11:55:17 continue [main]
    11:55:17 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl logs nginx-ro-root-65f7f86764-wr675"}
    11:55:18 started  [sys.exec(3)] [input={"command":"kubectl logs nginx-ro-root-65f7f86764-wr675"}]
    11:55:18 sent     [sys.exec(3)]
            content  [3] content | /docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration
            content  [3] content | /docker-entrypoint.sh: Looking for shell scripts in /docker-entrypoint.d/
            content  [3] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
            content  [3] content | 10-listen-on-ipv6-by-default.sh: info: can not modify /etc/nginx/conf.d/default.conf (read-only file ...
            content  [3] content | /docker-entrypoint.sh: Sourcing /docker-entrypoint.d/15-local-resolvers.envsh
            content  [3] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/20-envsubst-on-templates.sh
            content  [3] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/30-tune-worker-processes.sh
            content  [3] content | /docker-entrypoint.sh: Configuration complete; ready for start up
            content  [3] content | 2025/04/18 15:54:11 [emerg] 1#1: mkdir() "/var/cache/nginx/client_temp" failed (30: Read-only file s ...
            content  [3] content | nginx: [emerg] mkdir() "/var/cache/nginx/client_temp" failed (30: Read-only file system)
            content  [3] content |
    11:55:18 ended    [sys.exec(3)] [output=/docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration\n/do...]
    11:55:18 continue [main]
    11:55:18 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl patch deployment nginx-ro-root -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"volumeMounts\":[{\"mountPath\":\"/var/cache/nginx\",\"name\":\"nginx-cache\"}]}],\"volumes\":[{\"name\":\"nginx-cache\",\"emptyDir\":{}}]}}}}}'"}
    11:55:20 started  [sys.exec(4)] [input={"command":"kubectl patch deployment nginx-ro-root -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"volumeMounts\":[{\"mountPath\":\"/var/cache/nginx\",\"name\":\"nginx-cache\"}]}],\"volumes\":[{\"name\":\"nginx-cache\",\"emptyDir\":{}}]}}}}}'"}]
    11:55:20 sent     [sys.exec(4)]
            content  [4] content | Error from server (BadRequest): invalid character '}' after top-level value
            content  [4] content |
    11:55:20 ended    [sys.exec(4)] [output=ERROR: exit status 1\nOUTPUT:\nError from server (BadRequest): invalid character '}' after top-level v...]
    11:55:20 continue [main]
    11:55:20 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl patch deployment nginx-ro-root -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"volumeMounts\":[{\"mountPath\":\"/var/cache/nginx\",\"name\":\"nginx-cache\"}]}],\"volumes\":[{\"name\":\"nginx-cache\",\"emptyDir\":{}}]}}}}'"}
    11:55:23 started  [sys.exec(5)] [input={"command":"kubectl patch deployment nginx-ro-root -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"volumeMounts\":[{\"mountPath\":\"/var/cache/nginx\",\"name\":\"nginx-cache\"}]}],\"volumes\":[{\"name\":\"nginx-cache\",\"emptyDir\":{}}]}}}}'"}]
    11:55:23 sent     [sys.exec(5)]
            content  [5] content | deployment.apps/nginx-ro-root patched
            content  [5] content |
    11:55:24 ended    [sys.exec(5)] [output=deployment.apps/nginx-ro-root patched]
    11:55:24 continue [main]
    11:55:24 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"sleep 15"}
    11:55:25 started  [sys.exec(6)] [input={"command":"sleep 15"}]
    11:55:25 sent     [sys.exec(6)]
    11:55:40 ended    [sys.exec(6)]
    11:55:40 continue [main]
    11:55:40 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pods"}
    11:55:41 started  [sys.exec(7)] [input={"command":"kubectl get pods"}]
    11:55:41 sent     [sys.exec(7)]
            content  [7] content | NAME                             READY   STATUS             RESTARTS      AGE
            content  [7] content | nginx-ro-root-65f7f86764-wr675   0/1     Error              5 (90s ago)   3m9s
            content  [7] content | nginx-ro-root-7897ccb456-dwkp4   0/1     CrashLoopBackOff   1 (13s ago)   17s
            content  [7] content |
    11:55:41 ended    [sys.exec(7)] [output=NAME                             READY   STATUS             RESTARTS      AGE\nnginx-ro-root-65f7f867...]
    11:55:41 continue [main]
    11:55:41 sent     [main]
            content  [1] content | Waiting for model response...         content  [1] content | I attempted to fix the issue with the nginx pod by patching the deployment to add a volume for caching. Here are the steps I took:
            content  [1] content |
            content  [1] content | 1. Analyzed the cluster using the command `k8sgpt analyze`, which indicated that the nginx pod had an error due to a read-only file system.
            content  [1] content | 2. Checked the pod logs with `kubectl logs nginx-ro-root-65f7f86764-wr675`, which confirmed that the nginx process was failing to create a directory due to the read-only file system.
            content  [1] content | 3. Attempted to patch the deployment to add a writable volume for nginx's cache using the `kubectl patch` command.
            content  [1] content | 4. Waited for 15 seconds to allow the changes to take effect.
            content  [1] content | 5. Checked the status of the pods again, but the nginx pod is still in an error state and another pod is in a CrashLoopBackOff state.
            content  [1] content |
            content  [1] content | The issue has not been resolved, and further investigation is needed.
    11:55:45 ended    [main] [output=I attempted to fix the issue with the nginx pod by patching the deployment to add a volume for cachi...]
    11:55:45 usage    [total=5041] [prompt=4615] [completion=426]

    OUTPUT:

    I attempted to fix the issue with the nginx pod by patching the deployment to add a volume for caching. Here are the steps I took:

    1. Analyzed the cluster using the command `k8sgpt analyze`, which indicated that the nginx pod had an error due to a read-only file system.
    2. Checked the pod logs with `kubectl logs nginx-ro-root-65f7f86764-wr675`, which confirmed that the nginx process was failing to create a directory due to the read-only file system.
    3. Attempted to patch the deployment to add a writable volume for nginx's cache using the `kubectl patch` command.
    4. Waited for 15 seconds to allow the changes to take effect.
    5. Checked the status of the pods again, but the nginx pod is still in an error state and another pod is in a CrashLoopBackOff state.

    The issue has not been resolved, and further investigation is needed.
    $
    $k get pods
    NAME                             READY   STATUS             RESTARTS      AGE
    nginx-ro-root-65f7f86764-wr675   0/1     CrashLoopBackOff   5 (29s ago)   3m32s
    nginx-ro-root-7897ccb456-dwkp4   0/1     CrashLoopBackOff   2 (20s ago)   40s

    ```

</details>

#### Second Attempt

Using a newer model `gpt-4.1-mini` succeded but it changed `securityContext` as you can see in the logs below as well as in the resultant [manifest](./misconfigured-nginx-ro-volume-scenario/fixed-ro-pod-with-security-context-change.yaml) it generated. This is not what we wanted and is an example of NOT providing very specific instructions to the LLM specifically about what NOT to do.

<details>
 <summary>Step by Step Process </summary>

- Using a better LLM model (`gpt-4.1-mini`) WORKS but it CHANGED `securityContext` which we do NOT want

    ```bash
    
    $k apply -f misconfigured-nginx-ro-volume-scenario/misconfigured-nginx-ro-root-volume.yaml
    deployment.apps/nginx-ro-root created
  
    $k get pods
    NAME                             READY   STATUS   RESTARTS   AGE
    nginx-ro-root-65f7f86764-8q8sv   0/1     Error    0          5s
 
    $gptscript --default-model=gpt-4.1-mini gptscript-instructions/k8sgpt-diag-fix.gpt
    12:05:59 WARNING: Changing the default model can have unknown behavior for existing tools. Use the model field per tool instead.
    12:05:59 started  [main]
    12:05:59 sent     [main]
    12:05:59 started  [sys.exec(2)] [input={"command":"k8sgpt analyze"}]
    12:05:59 sent     [sys.exec(2)]
            content  [2] content | AI Provider: AI not used; --explain not set
            content  [2] content |
            content  [2] content | 0: Pod default/nginx-ro-root-65f7f86764-8q8sv(Deployment/nginx-ro-root)
            content  [2] content | - Error: the last termination reason is Error container=nginx pod=nginx-ro-root-65f7f86764-8q8sv
            content  [2] content |
            content  [2] content |
            content  [2] content |
    12:05:59 ended    [sys.exec(2)] [output=AI Provider: AI not used; --explain not set\n\n0: Pod default/nginx-ro-root-65f7f86764-8q8sv(Deploymen...]
    12:05:59 continue [main]
    12:05:59 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pods -o wide"}
    12:06:00 started  [sys.exec(3)] [input={"command":"kubectl get pods -o wide"}]
    12:06:00 sent     [sys.exec(3)]
            content  [3] content | NAME                             READY   STATUS             RESTARTS      AGE   IP            NODE   ...
            content  [3] content | nginx-ro-root-65f7f86764-8q8sv   0/1     CrashLoopBackOff   1 (15s ago)   20s   10.244.0.17   ai-tro ...
            content  [3] content |
    12:06:00 ended    [sys.exec(3)] [output=NAME                             READY   STATUS             RESTARTS      AGE   IP            NODE...]
    12:06:00 continue [main]
    12:06:00 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl logs nginx-ro-root-65f7f86764-8q8sv"}
    12:06:01 started  [sys.exec(4)] [input={"command":"kubectl logs nginx-ro-root-65f7f86764-8q8sv"}]
    12:06:01 sent     [sys.exec(4)]
            content  [4] content | /docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration
            content  [4] content | /docker-entrypoint.sh: Looking for shell scripts in /docker-entrypoint.d/
            content  [4] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
            content  [4] content | 10-listen-on-ipv6-by-default.sh: info: can not modify /etc/nginx/conf.d/default.conf (read-only file ...
            content  [4] content | /docker-entrypoint.sh: Sourcing /docker-entrypoint.d/15-local-resolvers.envsh
            content  [4] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/20-envsubst-on-templates.sh
            content  [4] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/30-tune-worker-processes.sh
            content  [4] content | /docker-entrypoint.sh: Configuration complete; ready for start up
            content  [4] content | 2025/04/18 16:05:45 [emerg] 1#1: mkdir() "/var/cache/nginx/client_temp" failed (30: Read-only file s ...
            content  [4] content | nginx: [emerg] mkdir() "/var/cache/nginx/client_temp" failed (30: Read-only file system)
            content  [4] content |
    12:06:01 ended    [sys.exec(4)] [output=/docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration\n/do...]
    12:06:01 continue [main]
    12:06:01 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pod nginx-ro-root-65f7f86764-8q8sv -o yaml"}
    12:06:02 started  [sys.exec(5)] [input={"command":"kubectl get pod nginx-ro-root-65f7f86764-8q8sv -o yaml"}]
    12:06:02 sent     [sys.exec(5)]
            content  [5] content | apiVersion: v1
            content  [5] content | kind: Pod
            content  [5] content | metadata:
            content  [5] content |   creationTimestamp: "2025-04-18T16:05:40Z"
            content  [5] content |   generateName: nginx-ro-root-65f7f86764-
            content  [5] content |   labels:
            content  [5] content |     app: nginx
            content  [5] content |     pod-template-hash: 65f7f86764
            content  [5] content |   name: nginx-ro-root-65f7f86764-8q8sv
            content  [5] content |   namespace: default
            content  [5] content |   ownerReferences:
            content  [5] content |   - apiVersion: apps/v1
            content  [5] content |     blockOwnerDeletion: true
            content  [5] content |     controller: true
            content  [5] content |     kind: ReplicaSet
            content  [5] content |     name: nginx-ro-root-65f7f86764
            content  [5] content |     uid: f0e9ec71-5618-495c-b672-ba6abf222a95
            content  [5] content |   resourceVersion: "8809"
            content  [5] content |   uid: 7fa16785-6743-4922-9d5e-9fb772e7aebb
            content  [5] content | spec:
            content  [5] content |   containers:
            content  [5] content |   - image: nginx
            content  [5] content |     imagePullPolicy: Always
            content  [5] content |     name: nginx
            content  [5] content |     ports:
            content  [5] content |     - containerPort: 80
            content  [5] content |       protocol: TCP
            content  [5] content |     resources: {}
            content  [5] content |     securityContext:
            content  [5] content |       readOnlyRootFilesystem: true
            content  [5] content |     terminationMessagePath: /dev/termination-log
            content  [5] content |     terminationMessagePolicy: File
            content  [5] content |     volumeMounts:
            content  [5] content |     - mountPath: /var/run/secrets/kubernetes.io/serviceaccount
            content  [5] content |       name: kube-api-access-2zhwh
            content  [5] content |       readOnly: true
            content  [5] content |   dnsPolicy: ClusterFirst
            content  [5] content |   enableServiceLinks: true
            content  [5] content |   nodeName: ai-troubleshooting-control-plane
            content  [5] content |   preemptionPolicy: PreemptLowerPriority
            content  [5] content |   priority: 0
            content  [5] content |   restartPolicy: Always
            content  [5] content |   schedulerName: default-scheduler
            content  [5] content |   securityContext: {}
            content  [5] content |   serviceAccount: default
            content  [5] content |   serviceAccountName: default
            content  [5] content |   terminationGracePeriodSeconds: 30
            content  [5] content |   tolerations:
            content  [5] content |   - effect: NoExecute
            content  [5] content |     key: node.kubernetes.io/not-ready
            content  [5] content |     operator: Exists
            content  [5] content |     tolerationSeconds: 300
            content  [5] content |   - effect: NoExecute
            content  [5] content |     key: node.kubernetes.io/unreachable
            content  [5] content |     operator: Exists
            content  [5] content |     tolerationSeconds: 300
            content  [5] content |   volumes:
            content  [5] content |   - name: kube-api-access-2zhwh
            content  [5] content |     projected:
            content  [5] content |       defaultMode: 420
            content  [5] content |       sources:
            content  [5] content |       - serviceAccountToken:
            content  [5] content |           expirationSeconds: 3607
            content  [5] content |           path: token
            content  [5] content |       - configMap:
            content  [5] content |           items:
            content  [5] content |           - key: ca.crt
            content  [5] content |             path: ca.crt
            content  [5] content |           name: kube-root-ca.crt
            content  [5] content |       - downwardAPI:
            content  [5] content |           items:
            content  [5] content |           - fieldRef:
            content  [5] content |               apiVersion: v1
            content  [5] content |               fieldPath: metadata.namespace
            content  [5] content |             path: namespace
            content  [5] content | status:
            content  [5] content |   conditions:
            content  [5] content |   - lastProbeTime: null
            content  [5] content |     lastTransitionTime: "2025-04-18T16:05:43Z"
            content  [5] content |     status: "True"
            content  [5] content |     type: PodReadyToStartContainers
            content  [5] content |   - lastProbeTime: null
            content  [5] content |     lastTransitionTime: "2025-04-18T16:05:40Z"
            content  [5] content |     status: "True"
            content  [5] content |     type: Initialized
            content  [5] content |   - lastProbeTime: null
            content  [5] content |     lastTransitionTime: "2025-04-18T16:05:44Z"
            content  [5] content |     message: 'containers with unready status: [nginx]'
            content  [5] content |     reason: ContainersNotReady
            content  [5] content |     status: "False"
            content  [5] content |     type: Ready
            content  [5] content |   - lastProbeTime: null
            content  [5] content |     lastTransitionTime: "2025-04-18T16:05:44Z"
            content  [5] content |     message: 'containers with unready status: [nginx]'
            content  [5] content |     reason: ContainersNotReady
            content  [5] content |     status: "False"
            content  [5] content |     type: ContainersReady
            content  [5] content |   - lastProbeTime: null
            content  [5] content |     lastTransitionTime: "2025-04-18T16:05:40Z"
            content  [5] content |     status: "True"
            content  [5] content |     type: PodScheduled
            content  [5] content |   containerStatuses:
            content  [5] content |   - containerID: containerd://7bba2291df33a02eb34690c1a1cc543273690b722ba5ff17c334901e47fe1320
            content  [5] content |     image: docker.io/library/nginx:latest
            content  [5] content |     imageID: docker.io/library/nginx@sha256:5ed8fcc66f4ed123c1b2560ed708dc148755b6e4cbd8b943fab094f2 ...
            content  [5] content |     lastState:
            content  [5] content |       terminated:
            content  [5] content |         containerID: containerd://7bba2291df33a02eb34690c1a1cc543273690b722ba5ff17c334901e47fe1320
            content  [5] content |         exitCode: 1
            content  [5] content |         finishedAt: "2025-04-18T16:05:45Z"
            content  [5] content |         reason: Error
            content  [5] content |         startedAt: "2025-04-18T16:05:45Z"
            content  [5] content |     name: nginx
            content  [5] content |     ready: false
            content  [5] content |     restartCount: 1
            content  [5] content |     started: false
            content  [5] content |     state:
            content  [5] content |       waiting:
            content  [5] content |         message: back-off 10s restarting failed container=nginx pod=nginx-ro-root-65f7f86764-8q8sv_d ...
            content  [5] content |         reason: CrashLoopBackOff
            content  [5] content |     volumeMounts:
            content  [5] content |     - mountPath: /var/run/secrets/kubernetes.io/serviceaccount
            content  [5] content |       name: kube-api-access-2zhwh
            content  [5] content |       readOnly: true
            content  [5] content |       recursiveReadOnly: Disabled
            content  [5] content |   hostIP: 192.168.132.2
            content  [5] content |   hostIPs:
            content  [5] content |   - ip: 192.168.132.2
            content  [5] content |   phase: Running
            content  [5] content |   podIP: 10.244.0.17
            content  [5] content |   podIPs:
            content  [5] content |   - ip: 10.244.0.17
            content  [5] content |   qosClass: BestEffort
            content  [5] content |   startTime: "2025-04-18T16:05:40Z"
            content  [5] content |
    12:06:02 ended    [sys.exec(5)] [output=apiVersion: v1\nkind: Pod\nmetadata:\n  creationTimestamp: \"2025-04-18T16:05:40Z\"\n  generateName: nginx...]
    12:06:02 continue [main]
    12:06:02 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl patch deployment nginx-ro-root -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"securityContext\":{\"readOnlyRootFilesystem\":false}}]}}}}'"}
    12:06:03 started  [sys.exec(6)] [input={"command":"kubectl patch deployment nginx-ro-root -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"securityContext\":{\"readOnlyRootFilesystem\":false}}]}}}}'"}]
    12:06:03 sent     [sys.exec(6)]
            content  [6] content | deployment.apps/nginx-ro-root patched
            content  [6] content |
    12:06:03 ended    [sys.exec(6)] [output=deployment.apps/nginx-ro-root patched]
    12:06:03 continue [main]
    12:06:03 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"sleep 15"}
    12:06:03 started  [sys.exec(7)] [input={"command":"sleep 15"}]
    12:06:03 sent     [sys.exec(7)]
    12:06:18 ended    [sys.exec(7)]
    12:06:18 continue [main]
    12:06:18 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pods"}
    12:06:19 started  [sys.exec(8)] [input={"command":"kubectl get pods"}]
    12:06:19 sent     [sys.exec(8)]
            content  [8] content | NAME                             READY   STATUS    RESTARTS   AGE
            content  [8] content | nginx-ro-root-8647b7bb85-jnsxj   1/1     Running   0          16s
            content  [8] content |
    12:06:19 ended    [sys.exec(8)] [output=NAME                             READY   STATUS    RESTARTS   AGE\nnginx-ro-root-8647b7bb85-jnsxj   1...]
    12:06:19 continue [main]
    12:06:19 sent     [main]
            content  [1] content | Waiting for model response...         content  [1] content | I analyzed the cluster with "k8sgpt analyze" and found a pod with a CrashLoopBackOff error. Checking the pod logs showed that the nginx container was failing due to a read-only file system error when trying to create a directory. Inspecting the pod spec revealed that the container had the securityContext.readOnlyRootFilesystem set to true, causing the issue.
            content  [1] content |
            content  [1] content | I patched the deployment "nginx-ro-root" to set securityContext.readOnlyRootFilesystem to false for the nginx container. After waiting 15 seconds, the new pod started successfully and is now running without errors.
    12:06:21 ended    [main] [output=I analyzed the cluster with \"k8sgpt analyze\" and found a pod with a CrashLoopBackOff error. Checking...]
    12:06:21 usage    [total=10609] [prompt=10317] [completion=292]

    OUTPUT:

    I analyzed the cluster with "k8sgpt analyze" and found a pod with a CrashLoopBackOff error. Checking the pod logs showed that the nginx container was failing due to a read-only file system error when trying to create a directory. Inspecting the pod spec revealed that the container had the securityContext.readOnlyRootFilesystem set to true, causing the issue.

    I patched the deployment "nginx-ro-root" to set securityContext.readOnlyRootFilesystem to false for the nginx container. After waiting 15 seconds, the new pod started successfully and is now running without errors.
    ```
- Verify that the problem is fixed
    ```bash
    $k get pods
    NAME                             READY   STATUS    RESTARTS   AGE
    nginx-ro-root-8647b7bb85-jnsxj   1/1     Running   0          26s
    $
    ```
</details>

#### Third Attempt

Retry second attemt with specific instructions to LLM asking NOT to make changes to `securityContext`. It did fix the problem and this is resultant [manifest](./misconfigured-nginx-ro-volume-scenario/fixed-ro-pod.yaml) it generated.  

<details>
 <summary>Step by Step Process </summary>

Since the problem was fixed in the previous ttempt, I re-introduced the problem by re-applying the manifest and then modifed the gptscript instructions to specifiically not to change `securityContext` of the pod as you can see in the logs below. 

- Using gpt-4.1-mini model but with instructions to LLM NOT to make any changes to `securityContext`

    ```bash
    $cat gptscript-instructions/k8sgpt-diag-fix-no-security-context-changes.gpt
    tools: sys.exec?
    description: A kubernetes system admin

    Do the following sequentially, do not run in parallel

    1. You are a kubernetes system admin with kubectl command available to you
    2. Use "k8sgpt analyze" command to check if there are any problems with the cluster or pods running.
    3. Use "kubectl" command to check if there are any issues. Check pod logs to see if there are any issues.
    4. Do not make any changes to "securityContext" of the pod spec.
    4. Do not use "kubectl edit" command to make changes.
    5. Only use "kubectl patch" command to make changes.
    6. Wait for 15 seconds to verify that the changes you made fixed the problem
    7. Provide details on steps you took to fix the problem
    ```

- Verify that the problem exists

    ```bash
    $k get pods
    No resources found in default namespace.
 
    $k apply -f misconfigured-nginx-ro-volume-scenario/misconfigured-nginx-ro-root-volume.yaml
    deployment.apps/nginx-ro-root created
 
    $k get pods
    NAME                             READY   STATUS   RESTARTS   AGE
    nginx-ro-root-65f7f86764-ngqs8   0/1     Error    0          5s
 
    $k logs nginx-ro-root-65f7f86764-ngqs8
    /docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration
    /docker-entrypoint.sh: Looking for shell scripts in /docker-entrypoint.d/
    /docker-entrypoint.sh: Launching /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
    10-listen-on-ipv6-by-default.sh: info: can not modify /etc/nginx/conf.d/default.conf (read-only file system?)
    /docker-entrypoint.sh: Sourcing /docker-entrypoint.d/15-local-resolvers.envsh
    /docker-entrypoint.sh: Launching /docker-entrypoint.d/20-envsubst-on-templates.sh
    /docker-entrypoint.sh: Launching /docker-entrypoint.d/30-tune-worker-processes.sh
    /docker-entrypoint.sh: Configuration complete; ready for start up
    2025/04/18 16:16:26 [emerg] 1#1: mkdir() "/var/cache/nginx/client_temp" failed (30: Read-only file system)
    nginx: [emerg] mkdir() "/var/cache/nginx/client_temp" failed (30: Read-only file system)
    

    $k8sgpt analyze
    AI Provider: AI not used; --explain not set

    0: Pod default/nginx-ro-root-65f7f86764-ngqs8(Deployment/nginx-ro-root)
    - Error: the last termination reason is Error container=nginx pod=nginx-ro-root-65f7f86764-ngqs8
    ```
- Run gptscript command to fix the issue 
    ```bash
    $gptscript --default-model=gpt-4.1-mini gptscript-instructions/k8sgpt-diag-fix-no-security-context-changes.gpt
    12:17:02 WARNING: Changing the default model can have unknown behavior for existing tools. Use the model field per tool instead.
    12:17:02 started  [main]
    12:17:02 sent     [main]
    12:17:02 started  [sys.exec(2)] [input={"command":"k8sgpt analyze"}]
    12:17:02 sent     [sys.exec(2)]
            content  [2] content | AI Provider: AI not used; --explain not set
            content  [2] content |
            content  [2] content | 0: Pod default/nginx-ro-root-65f7f86764-ngqs8(Deployment/nginx-ro-root)
            content  [2] content | - Error: the last termination reason is Error container=nginx pod=nginx-ro-root-65f7f86764-ngqs8
            content  [2] content |
            content  [2] content |
            content  [2] content |
    12:17:02 ended    [sys.exec(2)] [output=AI Provider: AI not used; --explain not set\n\n0: Pod default/nginx-ro-root-65f7f86764-ngqs8(Deploymen...]
    12:17:02 continue [main]
    12:17:02 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pods -o wide"}
    12:17:03 started  [sys.exec(3)] [input={"command":"kubectl get pods -o wide"}]
    12:17:03 sent     [sys.exec(3)]
            content  [3] content | NAME                             READY   STATUS             RESTARTS      AGE   IP            NODE   ...
            content  [3] content | nginx-ro-root-65f7f86764-ngqs8   0/1     CrashLoopBackOff   2 (22s ago)   41s   10.244.0.19   ai-tro ...
            content  [3] content |
    12:17:03 ended    [sys.exec(3)] [output=NAME                             READY   STATUS             RESTARTS      AGE   IP            NODE...]
    12:17:03 continue [main]
    12:17:03 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl logs nginx-ro-root-65f7f86764-ngqs8"}
    12:17:04 started  [sys.exec(4)] [input={"command":"kubectl logs nginx-ro-root-65f7f86764-ngqs8"}]
    12:17:04 sent     [sys.exec(4)]
            content  [4] content | /docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration
            content  [4] content | /docker-entrypoint.sh: Looking for shell scripts in /docker-entrypoint.d/
            content  [4] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
            content  [4] content | 10-listen-on-ipv6-by-default.sh: info: can not modify /etc/nginx/conf.d/default.conf (read-only file ...
            content  [4] content | /docker-entrypoint.sh: Sourcing /docker-entrypoint.d/15-local-resolvers.envsh
            content  [4] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/20-envsubst-on-templates.sh
            content  [4] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/30-tune-worker-processes.sh
            content  [4] content | /docker-entrypoint.sh: Configuration complete; ready for start up
            content  [4] content | 2025/04/18 16:16:41 [emerg] 1#1: mkdir() "/var/cache/nginx/client_temp" failed (30: Read-only file s ...
            content  [4] content | nginx: [emerg] mkdir() "/var/cache/nginx/client_temp" failed (30: Read-only file system)
            content  [4] content |
    12:17:04 ended    [sys.exec(4)] [output=/docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration\n/do...]
    12:17:04 continue [main]
    12:17:04 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pod nginx-ro-root-65f7f86764-ngqs8 -o jsonpath='{.spec.volumes}'"}
    12:17:06 started  [sys.exec(5)] [input={"command":"kubectl get pod nginx-ro-root-65f7f86764-ngqs8 -o jsonpath='{.spec.volumes}'"}]
    12:17:06 sent     [sys.exec(5)]
            content  [5] content | [{"name":"kube-api-access-n8kzl","projected":{"defaultMode":420,"sources":[{"serviceAccountToken":{" ...
    12:17:06 ended    [sys.exec(5)] [output=[{\"name\":\"kube-api-access-n8kzl\",\"projected\":{\"defaultMode\":420,\"sources\":[{\"serviceAccountToken\":{\"...]
    12:17:06 continue [main]
    12:17:06 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pod nginx-ro-root-65f7f86764-ngqs8 -o jsonpath='{.spec.containers[0].volumeMounts}'"}
    12:17:07 started  [sys.exec(6)] [input={"command":"kubectl get pod nginx-ro-root-65f7f86764-ngqs8 -o jsonpath='{.spec.containers[0].volumeMounts}'"}]
    12:17:07 sent     [sys.exec(6)]
            content  [6] content | [{"mountPath":"/var/run/secrets/kubernetes.io/serviceaccount","name":"kube-api-access-n8kzl","readOn ...
    12:17:07 ended    [sys.exec(6)] [output=[{\"mountPath\":\"/var/run/secrets/kubernetes.io/serviceaccount\",\"name\":\"kube-api-access-n8kzl\",\"readOn...]
    12:17:07 continue [main]
    12:17:07 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl patch deployment nginx-ro-root -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"volumeMounts\":[{\"name\":\"cache-volume\",\"mountPath\":\"/var/cache/nginx\"}]}],\"volumes\":[{\"name\":\"cache-volume\",\"emptyDir\":{}}]}}}}'"}
    12:17:09 started  [sys.exec(7)] [input={"command":"kubectl patch deployment nginx-ro-root -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"volumeMounts\":[{\"name\":\"cache-volume\",\"mountPath\":\"/var/cache/nginx\"}]}],\"volumes\":[{\"name\":\"cache-volume\",\"emptyDir\":{}}]}}}}'"}]
    12:17:09 sent     [sys.exec(7)]
            content  [7] content | deployment.apps/nginx-ro-root patched
            content  [7] content |
    12:17:09 ended    [sys.exec(7)] [output=deployment.apps/nginx-ro-root patched]
    12:17:09 continue [main]
    12:17:09 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"sleep 15"}
    12:17:10 started  [sys.exec(8)] [input={"command":"sleep 15"}]
    12:17:10 sent     [sys.exec(8)]
    12:17:25 ended    [sys.exec(8)]
    12:17:25 continue [main]
    12:17:25 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pods -l app=nginx-ro-root"}
    12:17:26 started  [sys.exec(9)] [input={"command":"kubectl get pods -l app=nginx-ro-root"}]
    12:17:26 sent     [sys.exec(9)]
            content  [9] content | No resources found in default namespace.
            content  [9] content |
    12:17:26 ended    [sys.exec(9)] [output=No resources found in default namespace.]
    12:17:26 continue [main]
    12:17:26 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pods"}
    12:17:27 started  [sys.exec(10)] [input={"command":"kubectl get pods"}]
    12:17:27 sent     [sys.exec(10)]
            content  [10] content | NAME                            READY   STATUS             RESTARTS      AGE
            content  [10] content | nginx-ro-root-985fd5ccb-wt8ql   0/1     CrashLoopBackOff   1 (11s ago)   18s
            content  [10] content |
    12:17:27 ended    [sys.exec(10)] [output=NAME                            READY   STATUS             RESTARTS      AGE\nnginx-ro-root-985fd5ccb...]
    12:17:27 continue [main]
    12:17:27 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl logs nginx-ro-root-985fd5ccb-wt8ql"}
    12:17:28 started  [sys.exec(11)] [input={"command":"kubectl logs nginx-ro-root-985fd5ccb-wt8ql"}]
    12:17:28 sent     [sys.exec(11)]
            content  [11] content | /docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration
            content  [11] content | /docker-entrypoint.sh: Looking for shell scripts in /docker-entrypoint.d/
            content  [11] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
            content  [11] content | 10-listen-on-ipv6-by-default.sh: info: can not modify /etc/nginx/conf.d/default.conf (read-only file ...
            content  [11] content | /docker-entrypoint.sh: Sourcing /docker-entrypoint.d/15-local-resolvers.envsh
            content  [11] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/20-envsubst-on-templates.sh
            content  [11] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/30-tune-worker-processes.sh
            content  [11] content | /docker-entrypoint.sh: Configuration complete; ready for start up
            content  [11] content | 2025/04/18 16:17:16 [notice] 1#1: using the "epoll" event method
            content  [11] content | 2025/04/18 16:17:16 [notice] 1#1: nginx/1.27.5
            content  [11] content | 2025/04/18 16:17:16 [notice] 1#1: built by gcc 12.2.0 (Debian 12.2.0-14)
            content  [11] content | 2025/04/18 16:17:16 [notice] 1#1: OS: Linux 5.15.0-106-generic
            content  [11] content | 2025/04/18 16:17:16 [notice] 1#1: getrlimit(RLIMIT_NOFILE): 1048576:1048576
            content  [11] content | 2025/04/18 16:17:16 [emerg] 1#1: open() "/run/nginx.pid" failed (30: Read-only file system)
            content  [11] content | nginx: [emerg] open() "/run/nginx.pid" failed (30: Read-only file system)
            content  [11] content |
    12:17:28 ended    [sys.exec(11)] [output=/docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration\n/do...]
    12:17:28 continue [main]
    12:17:28 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pod nginx-ro-root-985fd5ccb-wt8ql -o jsonpath='{.spec.volumes}'"}
    12:17:29 started  [sys.exec(12)] [input={"command":"kubectl get pod nginx-ro-root-985fd5ccb-wt8ql -o jsonpath='{.spec.volumes}'"}]
    12:17:29 sent     [sys.exec(12)]
            content  [12] content | [{"emptyDir":{},"name":"cache-volume"},{"name":"kube-api-access-l2sms","projected":{"defaultMode":42 ...
    12:17:29 ended    [sys.exec(12)] [output=[{\"emptyDir\":{},\"name\":\"cache-volume\"},{\"name\":\"kube-api-access-l2sms\",\"projected\":{\"defaultMode\":42...]
    12:17:29 continue [main]
    12:17:29 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pod nginx-ro-root-985fd5ccb-wt8ql -o jsonpath='{.spec.containers[0].volumeMounts}'"}
    12:17:31 started  [sys.exec(13)] [input={"command":"kubectl get pod nginx-ro-root-985fd5ccb-wt8ql -o jsonpath='{.spec.containers[0].volumeMounts}'"}]
    12:17:31 sent     [sys.exec(13)]
            content  [13] content | [{"mountPath":"/var/cache/nginx","name":"cache-volume"},{"mountPath":"/var/run/secrets/kubernetes.io ...
    12:17:31 ended    [sys.exec(13)] [output=[{\"mountPath\":\"/var/cache/nginx\",\"name\":\"cache-volume\"},{\"mountPath\":\"/var/run/secrets/kubernetes.io...]
    12:17:31 continue [main]
    12:17:31 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl patch deployment nginx-ro-root -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"volumeMounts\":[{\"name\":\"run-volume\",\"mountPath\":\"/run\"}]}],\"volumes\":[{\"name\":\"run-volume\",\"emptyDir\":{}}]}}}}'"}
    12:17:34 started  [sys.exec(14)] [input={"command":"kubectl patch deployment nginx-ro-root -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"nginx\",\"volumeMounts\":[{\"name\":\"run-volume\",\"mountPath\":\"/run\"}]}],\"volumes\":[{\"name\":\"run-volume\",\"emptyDir\":{}}]}}}}'"}]
    12:17:34 sent     [sys.exec(14)]
            content  [14] content | deployment.apps/nginx-ro-root patched
            content  [14] content |
    12:17:35 ended    [sys.exec(14)] [output=deployment.apps/nginx-ro-root patched]
    12:17:35 continue [main]
    12:17:35 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"sleep 15"}
    12:17:35 started  [sys.exec(15)] [input={"command":"sleep 15"}]
    12:17:35 sent     [sys.exec(15)]
    12:17:50 ended    [sys.exec(15)]
    12:17:50 continue [main]
    12:17:50 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pods"}
    12:17:51 started  [sys.exec(16)] [input={"command":"kubectl get pods"}]
    12:17:51 sent     [sys.exec(16)]
            content  [16] content | NAME                             READY   STATUS    RESTARTS   AGE
            content  [16] content | nginx-ro-root-7775896c68-g5bks   1/1     Running   0          16s
            content  [16] content |
    12:17:51 ended    [sys.exec(16)] [output=NAME                             READY   STATUS    RESTARTS   AGE\nnginx-ro-root-7775896c68-g5bks   1...]
    12:17:51 continue [main]
    12:17:51 sent     [main]
            content  [1] content | Waiting for model response...         content  [1] content | I analyzed the cluster and found the pod nginx-ro-root was crashing due to a read-only file system error when trying to create directories and files under /var/cache/nginx and /run.
            content  [1] content |
            content  [1] content | I patched the deployment to add emptyDir volumes mounted at /var/cache/nginx and /run to provide writable storage for these paths.
            content  [1] content |
            content  [1] content | After waiting 15 seconds, the new pod started successfully and is now running without errors.
            content  [1] content |
            content  [1] content | Summary of steps taken:
            content  [1] content | 1. Used k8sgpt analyze to identify pod crash.
            content  [1] content | 2. Checked pod logs to find read-only file system errors for /var/cache/nginx and /run.
            content  [1] content | 3. Patched deployment to add emptyDir volumes mounted at /var/cache/nginx and /run.
            content  [1] content | 4. Waited 15 seconds and verified pod is running successfully.
    12:17:55 ended    [main] [output=I analyzed the cluster and found the pod nginx-ro-root was crashing due to a read-only file system e...]
    12:17:55 usage    [total=20680] [prompt=20021] [completion=659]

    OUTPUT:

    I analyzed the cluster and found the pod nginx-ro-root was crashing due to a read-only file system error when trying to create directories and files under /var/cache/nginx and /run.

    I patched the deployment to add emptyDir volumes mounted at /var/cache/nginx and /run to provide writable storage for these paths.

    After waiting 15 seconds, the new pod started successfully and is now running without errors.

    Summary of steps taken:
    1. Used k8sgpt analyze to identify pod crash.
    2. Checked pod logs to find read-only file system errors for /var/cache/nginx and /run.
    3. Patched deployment to add emptyDir volumes mounted at /var/cache/nginx and /run.
    4. Waited 15 seconds and verified pod is running successfully.
    $
    ```
    
    - verify that the problem has been fixed

    ```bash
    $k get pods
    NAME                             READY   STATUS    RESTARTS   AGE
    nginx-ro-root-7775896c68-g5bks   1/1     Running   0          28s
    $
    $k logs nginx-ro-root-7775896c68-g5bks
    /docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration
    /docker-entrypoint.sh: Looking for shell scripts in /docker-entrypoint.d/
    /docker-entrypoint.sh: Launching /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
    10-listen-on-ipv6-by-default.sh: info: can not modify /etc/nginx/conf.d/default.conf (read-only file system?)
    /docker-entrypoint.sh: Sourcing /docker-entrypoint.d/15-local-resolvers.envsh
    /docker-entrypoint.sh: Launching /docker-entrypoint.d/20-envsubst-on-templates.sh
    /docker-entrypoint.sh: Launching /docker-entrypoint.d/30-tune-worker-processes.sh
    /docker-entrypoint.sh: Configuration complete; ready for start up
    2025/04/18 16:17:37 [notice] 1#1: using the "epoll" event method
    2025/04/18 16:17:37 [notice] 1#1: nginx/1.27.5
    2025/04/18 16:17:37 [notice] 1#1: built by gcc 12.2.0 (Debian 12.2.0-14)
    2025/04/18 16:17:37 [notice] 1#1: OS: Linux 5.15.0-106-generic
    2025/04/18 16:17:37 [notice] 1#1: getrlimit(RLIMIT_NOFILE): 1048576:1048576
    2025/04/18 16:17:37 [notice] 1#1: start worker processes
    2025/04/18 16:17:37 [notice] 1#1: start worker process 28
    2025/04/18 16:17:37 [notice] 1#1: start worker process 29
    2025/04/18 16:17:37 [notice] 1#1: start worker process 30
    2025/04/18 16:17:37 [notice] 1#1: start worker process 31
    2025/04/18 16:17:37 [notice] 1#1: start worker process 32
    2025/04/18 16:17:37 [notice] 1#1: start worker process 33
    2025/04/18 16:17:37 [notice] 1#1: start worker process 34
    2025/04/18 16:17:37 [notice] 1#1: start worker process 35
    2025/04/18 16:17:37 [notice] 1#1: start worker process 36
    2025/04/18 16:17:37 [notice] 1#1: start worker process 37
    2025/04/18 16:17:37 [notice] 1#1: start worker process 38
    2025/04/18 16:17:37 [notice] 1#1: start worker process 39

    ```
</details>


### SCENARIO-3: Troubleshooting mis-configured label issue 

In this scenario we will apply [this deployment](./misconfigured-nginx-service-label/misconfigured-label.yaml) which has a nginx deployment but with mis-configured service label. Most of the time this was an easy one for LLM to fix.

<details>
 <summary>Step by Step Process </summary>
    
- apply manifests to introduce the problem

    ```bash
    $k apply -f misconfigured-nginx-service-label/misconfigured-label.yaml
    deployment.apps/nginx created
    service/nginx created
    $
    $k get pods,svc
    NAME                         READY   STATUS    RESTARTS   AGE
    pod/nginx-6864f89447-ppmln   0/1     Running   0          4s

    NAME                 TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)   AGE
    service/kubernetes   ClusterIP   10.96.0.1    <none>        443/TCP   143m
    service/nginx        ClusterIP   10.96.2.81   <none>        80/TCP    5s
    $
    $k get pods,svc,ep
    NAME                         READY   STATUS    RESTARTS   AGE
    pod/nginx-6864f89447-ppmln   0/1     Running   0          13s

    NAME                 TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)   AGE
    service/kubernetes   ClusterIP   10.96.0.1    <none>        443/TCP   143m
    service/nginx        ClusterIP   10.96.2.81   <none>        80/TCP    14s

    NAME                   ENDPOINTS            AGE
    endpoints/kubernetes   192.168.132.2:6443   143m
    endpoints/nginx        <none>               13s
    $
    $k8sgpt  analyze
    AI Provider: AI not used; --explain not set

    0: Service default/nginx()
    - Error: Service has no endpoints, expected label app=nginx007
    ```
- run gptscript command  
    ```bash
    $gptscript --default-model=gpt-4.1-mini gptscript-instructions/k8sgpt-diag-fix-no-security-context-changes.gpt
    12:50:32 WARNING: Changing the default model can have unknown behavior for existing tools. Use the model field per tool instead.
    12:50:32 started  [main]
    12:50:32 sent     [main]
    12:50:32 started  [sys.exec(2)] [input={"command":"k8sgpt analyze"}]
    12:50:32 sent     [sys.exec(2)]
            content  [2] content | AI Provider: AI not used; --explain not set
            content  [2] content |
            content  [2] content | 0: Service default/nginx()
            content  [2] content | - Error: Service has no endpoints, expected label app=nginx007
            content  [2] content |
            content  [2] content |
            content  [2] content |
    12:50:32 ended    [sys.exec(2)] [output=AI Provider: AI not used; --explain not set\n\n0: Service default/nginx()\n- Error: Service has no endp...]
    12:50:32 continue [main]
    12:50:32 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pods --all-namespaces"}
    12:50:34 started  [sys.exec(3)] [input={"command":"kubectl get pods --all-namespaces"}]
    12:50:34 sent     [sys.exec(3)]
            content  [3] content | NAMESPACE            NAME                                                       READY   STATUS    RE ...
            content  [3] content | default              nginx-6864f89447-ppmln                                     1/1     Running   0  ...
            content  [3] content | kube-system          coredns-668d6bf9bc-4rrx5                                   1/1     Running   0  ...
            content  [3] content | kube-system          coredns-668d6bf9bc-qpl8r                                   1/1     Running   0  ...
            content  [3] content | kube-system          etcd-ai-troubleshooting-control-plane                      1/1     Running   0  ...
            content  [3] content | kube-system          kindnet-q79qc                                              1/1     Running   0  ...
            content  [3] content | kube-system          kube-apiserver-ai-troubleshooting-control-plane            1/1     Running   0  ...
            content  [3] content | kube-system          kube-controller-manager-ai-troubleshooting-control-plane   1/1     Running   0  ...
            content  [3] content | kube-system          kube-proxy-krgzz                                           1/1     Running   0  ...
            content  [3] content | kube-system          kube-scheduler-ai-troubleshooting-control-plane            1/1     Running   0  ...
            content  [3] content | local-path-storage   local-path-provisioner-7dc846544d-gm7dx                    1/1     Running   0  ...
            content  [3] content |
    12:50:34 ended    [sys.exec(3)] [output=NAMESPACE            NAME                                                       READY   STATUS    RE...]
    12:50:34 continue [main]
    12:50:34 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get svc -n default"}
    12:50:34 started  [sys.exec(4)] [input={"command":"kubectl get svc -n default"}]
    12:50:34 sent     [sys.exec(4)]
            content  [4] content | NAME         TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)   AGE
            content  [4] content | kubernetes   ClusterIP   10.96.0.1    <none>        443/TCP   144m
            content  [4] content | nginx        ClusterIP   10.96.2.81   <none>        80/TCP    73s
            content  [4] content |
    12:50:35 ended    [sys.exec(4)] [output=NAME         TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)   AGE\nkubernetes   ClusterIP   10.96.0.1...]
    12:50:35 continue [main]
    12:50:35 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get endpoints -n default nginx"}
    12:50:35 started  [sys.exec(5)] [input={"command":"kubectl get endpoints -n default nginx"}]
    12:50:35 sent     [sys.exec(5)]
            content  [5] content | NAME    ENDPOINTS   AGE
            content  [5] content | nginx   <none>      72s
            content  [5] content |
    12:50:35 ended    [sys.exec(5)] [output=NAME    ENDPOINTS   AGE\nnginx   \u003cnone\u003e      72s]
    12:50:35 continue [main]
    12:50:35 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pods -n default -o jsonpath='{.items[?(@.metadata.labels.app==\"nginx007\")].metadata.name}'"}
    12:50:36 started  [sys.exec(6)] [input={"command":"kubectl get pods -n default -o jsonpath='{.items[?(@.metadata.labels.app==\"nginx007\")].metadata.name}'"}]
    12:50:36 sent     [sys.exec(6)]
    12:50:36 ended    [sys.exec(6)]
    12:50:36 continue [main]
    12:50:36 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get pods -n default --show-labels"}
    12:50:37 started  [sys.exec(7)] [input={"command":"kubectl get pods -n default --show-labels"}]
    12:50:37 sent     [sys.exec(7)]
            content  [7] content | NAME                     READY   STATUS    RESTARTS   AGE   LABELS
            content  [7] content | nginx-6864f89447-ppmln   1/1     Running   0          74s   app=nginx,pod-template-hash=6864f89447
            content  [7] content |
    12:50:37 ended    [sys.exec(7)] [output=NAME                     READY   STATUS    RESTARTS   AGE   LABELS\nnginx-6864f89447-ppmln   1/1...]
    12:50:37 continue [main]
    12:50:37 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl logs nginx-6864f89447-ppmln -n default"}
    12:50:38 started  [sys.exec(8)] [input={"command":"kubectl logs nginx-6864f89447-ppmln -n default"}]
    12:50:38 sent     [sys.exec(8)]
            content  [8] content | /docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration
            content  [8] content | /docker-entrypoint.sh: Looking for shell scripts in /docker-entrypoint.d/
            content  [8] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
            content  [8] content | 10-listen-on-ipv6-by-default.sh: info: Getting the checksum of /etc/nginx/conf.d/default.conf
            content  [8] content | 10-listen-on-ipv6-by-default.sh: info: Enabled listen on IPv6 in /etc/nginx/conf.d/default.conf
            content  [8] content | /docker-entrypoint.sh: Sourcing /docker-entrypoint.d/15-local-resolvers.envsh
            content  [8] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/20-envsubst-on-templates.sh
            content  [8] content | /docker-entrypoint.sh: Launching /docker-entrypoint.d/30-tune-worker-processes.sh
            content  [8] content | /docker-entrypoint.sh: Configuration complete; ready for start up
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: using the "epoll" event method
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: nginx/1.27.5
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: built by gcc 12.2.0 (Debian 12.2.0-14)
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: OS: Linux 5.15.0-106-generic
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: getrlimit(RLIMIT_NOFILE): 1048576:1048576
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: start worker processes
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: start worker process 36
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: start worker process 37
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: start worker process 38
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: start worker process 39
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: start worker process 40
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: start worker process 41
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: start worker process 42
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: start worker process 43
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: start worker process 44
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: start worker process 45
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: start worker process 46
            content  [8] content | 2025/04/18 16:49:25 [notice] 1#1: start worker process 47
            content  [8] content |
    12:50:38 ended    [sys.exec(8)] [output=/docker-entrypoint.sh: /docker-entrypoint.d/ is not empty, will attempt to perform configuration\n/do...]
    12:50:38 continue [main]
    12:50:38 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get svc nginx -n default -o jsonpath='{.spec.selector}'"}
    12:50:39 started  [sys.exec(9)] [input={"command":"kubectl get svc nginx -n default -o jsonpath='{.spec.selector}'"}]
    12:50:39 sent     [sys.exec(9)]
            content  [9] content | {"app":"nginx007"}
    12:50:39 ended    [sys.exec(9)] [output={\"app\":\"nginx007\"}]
    12:50:39 continue [main]
    12:50:39 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl patch svc nginx -n default -p '{\"spec\":{\"selector\":{\"app\":\"nginx\"}}}'"}
    12:50:40 started  [sys.exec(10)] [input={"command":"kubectl patch svc nginx -n default -p '{\"spec\":{\"selector\":{\"app\":\"nginx\"}}}'"}]
    12:50:40 sent     [sys.exec(10)]
            content  [10] content | service/nginx patched
            content  [10] content |
    12:50:40 ended    [sys.exec(10)] [output=service/nginx patched]
    12:50:40 continue [main]
    12:50:40 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"sleep 15"}
    12:50:41 started  [sys.exec(11)] [input={"command":"sleep 15"}]
    12:50:41 sent     [sys.exec(11)]
    12:50:56 ended    [sys.exec(11)]
    12:50:56 continue [main]
    12:50:56 sent     [main]
            content  [1] content | Waiting for model response...
            content  [1] content | <tool call> exec -> {"command":"kubectl get endpoints -n default nginx"}
    12:50:57 started  [sys.exec(12)] [input={"command":"kubectl get endpoints -n default nginx"}]
    12:50:57 sent     [sys.exec(12)]
            content  [12] content | NAME    ENDPOINTS        AGE
            content  [12] content | nginx   10.244.0.22:80   94s
            content  [12] content |
    12:50:57 ended    [sys.exec(12)] [output=NAME    ENDPOINTS        AGE\nnginx   10.244.0.22:80   94s]
    12:50:57 continue [main]
    12:50:57 sent     [main]
            content  [1] content | Waiting for model response...         content  [1] content | I found that the service "nginx" in the "default" namespace had a selector "app=nginx007" which did not match the label "app=nginx" on the running pod. This caused the service to have no endpoints. I patched the service selector to "app=nginx" to match the pod label. After waiting 15 seconds, the service now correctly shows the pod endpoint. This resolves the issue of the service having no endpoints.
    12:50:59 ended    [main] [output=I found that the service \"nginx\" in the \"default\" namespace had a selector \"app=nginx007\" which did...]
    12:50:59 usage    [total=14108] [prompt=13747] [completion=361]

    OUTPUT:

    I found that the service "nginx" in the "default" namespace had a selector "app=nginx007" which did not match the label "app=nginx" on the running pod. This caused the service to have no endpoints. I patched the service selector to "app=nginx" to match the pod label. After waiting 15 seconds, the service now correctly shows the pod endpoint. This resolves the issue of the service having no endpoints.
    ```
- verify the fix 
    ```bash
    $k get pods,svc,ep
    NAME                         READY   STATUS    RESTARTS   AGE
    pod/nginx-6864f89447-ppmln   1/1     Running   0          102s

    NAME                 TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)   AGE
    service/kubernetes   ClusterIP   10.96.0.1    <none>        443/TCP   144m
    service/nginx        ClusterIP   10.96.2.81   <none>        80/TCP    103s

    NAME                   ENDPOINTS            AGE
    endpoints/kubernetes   192.168.132.2:6443   144m
    endpoints/nginx        10.244.0.22:80       102s
    ```
</details>

## Conclusion

- AI tools like `k8sgpt` can accurately diagnose common Kubernetes issues and provide helpful explanations. The approach reduces manual debugging effort but still requires human oversight for complex or novel issues.
- Integrating LLM function/tool calling (using `gptscript` for now but MCP in future) enables automation of troubleshooting and fixes via `kubectl`.
- This AI-driven workflow is effective in local/test clusters for quick issue resolution but I would not call it ready for production use yet.  
- Non-determinism is a fundamental characteristic of modern artificial intelligence i.e. AI systems often yield different results even when presented with identical input. This is challenge since you are never sure what approach it will take to troubleshoot the problem and can be partially overcome with better **prompts**