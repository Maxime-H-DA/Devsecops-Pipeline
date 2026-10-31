provider "kind" {}

resource "kind_cluster" "rpg" {
  name           = "rpg-pipeline"
  wait_for_ready = true

  kind_config {
    kind        = "Cluster"
    api_version = "kind.x-k8s.io/v1alpha4"

    node {
      role = "control-plane"
    }
  }
}

provider "helm" {
  kubernetes = {
    config_path = kind_cluster.rpg.kubeconfig_path
  }
}

resource "helm_release" "kyverno" {
  name             = "kyverno"
  repository       = "https://kyverno.github.io/kyverno/"
  chart            = "kyverno"
  version          = "3.9.1"
  namespace        = "kyverno"
  create_namespace = true
  timeout          = 900
  values           = [yamlencode({ config = { maxContextSize = "2Mi" } })]
}

provider "kubectl" {
  config_path      = kind_cluster.rpg.kubeconfig_path
  load_config_file = true
}

resource "kubectl_manifest" "kyverno_policies" {
  for_each   = fileset("${path.module}/../policies", "*.yaml")
  yaml_body  = file("${path.module}/../policies/${each.value}")
  depends_on = [helm_release.kyverno]
}


resource "helm_release" "vault" {
  name             = "vault"
  repository       = "https://helm.releases.hashicorp.com"
  chart            = "vault"
  version          = "0.34.1"
  namespace        = "vault"
  create_namespace = true
  values           = [file("${path.module}/../vault/vault-values.yaml")]
  wait             = false
}


resource "kubectl_manifest" "rpg_namespace" {
  yaml_body = file("${path.module}/../k8s/00-namespace.yaml")
}


resource "helm_release" "monitoring" {
  name             = "monitoring"
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  version          = "92.13.0"
  namespace        = "monitoring"
  create_namespace = true
  values           = [file("${path.module}/../monitoring/values.yaml")]
  timeout          = 900
}


resource "kubectl_manifest" "rpg_podmonitor" {
  yaml_body  = file("${path.module}/../monitoring/rpg-api-podmonitor.yaml")
  depends_on = [helm_release.monitoring, kubectl_manifest.rpg_namespace]
}


resource "kubectl_manifest" "rpg_alerts" {
  yaml_body  = file("${path.module}/../monitoring/rpg-api-alerts.yaml")
  depends_on = [helm_release.monitoring, kubectl_manifest.rpg_namespace]
}


resource "helm_release" "falco" {
  name             = "falco"
  repository       = "https://falcosecurity.github.io/charts"
  chart            = "falco"
  version          = "9.2.1"
  namespace        = "falco"
  create_namespace = true
  values           = [file("${path.module}/../falco/values.yaml")]
  timeout          = 900
  depends_on       = [helm_release.monitoring]
}


resource "kubectl_manifest" "falco_alerts" {
  yaml_body  = file("${path.module}/../falco/falco-alerts.yaml")
  depends_on = [helm_release.falco, helm_release.monitoring]
}


resource "helm_release" "argocd" {
  name             = "argocd"
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = "10.11.1"
  namespace        = "argocd"
  create_namespace = true
  timeout          = 900
}

resource "kubectl_manifest" "argocd_app_rpg_api" {
  yaml_body     = file("${path.module}/../argocd/rpg-api.yaml")
  ignore_fields = ["spec.source.kustomize"]
  depends_on = [
    helm_release.argocd,
    kubectl_manifest.kyverno_policies,
    kubectl_manifest.rpg_namespace,
    helm_release.vault,
  ]
}


resource "helm_release" "argocd_image_updater" {
  name       = "argocd-image-updater"
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argocd-image-updater"
  version    = "1.3.2"
  namespace  = "argocd"
  timeout    = 900
  depends_on = [helm_release.argocd]
}

resource "kubectl_manifest" "argocd_image_updater_rpg_api" {
  yaml_body = file("${path.module}/../argocd/rpg-api-image-updater.yaml")
  depends_on = [
    helm_release.argocd_image_updater,
    kubectl_manifest.argocd_app_rpg_api,
  ]
}
