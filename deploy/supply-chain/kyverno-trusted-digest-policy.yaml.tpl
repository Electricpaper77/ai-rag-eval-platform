apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: agenttrust-trusted-digest
spec:
  validationFailureAction: Enforce
  background: false
  rules:
    - name: require-gate12-trusted-image
      match:
        any:
          - resources:
              kinds:
                - Pod
              namespaces:
                - gate12
      validate:
        message: image digest is not the CI-verified trusted digest
        foreach:
          - list: request.object.spec.containers[]
            pattern:
              image: "__TRUSTED_IMAGE__"
