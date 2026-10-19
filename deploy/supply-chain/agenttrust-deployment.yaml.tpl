apiVersion: apps/v1
kind: Deployment
metadata:
  name: agenttrust-gate12
  namespace: gate12
  labels:
    app.kubernetes.io/name: agenttrust
    app.kubernetes.io/part-of: agenttrust-iq
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: agenttrust
  template:
    metadata:
      labels:
        app.kubernetes.io/name: agenttrust
        app.kubernetes.io/part-of: agenttrust-iq
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: agenttrust-api
          image: __IMAGE_REFERENCE__
          imagePullPolicy: IfNotPresent
          command: ["gunicorn"]
          args:
            - backend.app.main:app
            - --bind
            - 0.0.0.0:8080
            - --workers
            - "1"
            - --worker-class
            - uvicorn.workers.UvicornWorker
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: PORT
              value: "8080"
            - name: INFERENCE_BACKEND
              value: mock
            - name: INFERENCE_ARTIFACTS_ROOT
              value: /tmp/inference_events
            - name: INFERENCE_LOG_PATH
              value: /tmp/inference_runs.jsonl
            - name: AGENTTRUST_ARTIFACT_DIR
              value: /tmp/agenttrust_artifacts
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            runAsGroup: 10001
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
            seccompProfile:
              type: RuntimeDefault
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 6
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 6
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: agenttrust
  namespace: gate12
  labels:
    app.kubernetes.io/name: agenttrust
    app.kubernetes.io/part-of: agenttrust-iq
spec:
  selector:
    app.kubernetes.io/name: agenttrust
  ports:
    - name: http
      port: 8080
      targetPort: http
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: agenttrust-gate12
  namespace: gate12
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: agenttrust
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app.kubernetes.io/part-of: agenttrust-iq
      ports:
        - protocol: TCP
          port: 8080
  egress: []
