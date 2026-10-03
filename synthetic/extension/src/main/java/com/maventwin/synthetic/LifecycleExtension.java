package com.maventwin.synthetic;

import org.apache.maven.AbstractMavenLifecycleParticipant;
import org.apache.maven.execution.MavenSession;
import org.apache.maven.model.Build;
import org.apache.maven.model.Plugin;
import org.apache.maven.model.PluginExecution;
import org.apache.maven.project.MavenProject;
import org.codehaus.plexus.component.annotations.Component;

@Component(role=org.apache.maven.AbstractMavenLifecycleParticipant.class, hint="com.maventwin.synthetic.LifecycleExtension")
public class LifecycleExtension extends AbstractMavenLifecycleParticipant {
  public void afterProjectsRead(MavenSession session) {
    for (MavenProject project : session.getProjects()) {
      Build build = project.getBuild();
      Plugin marker = new Plugin(); marker.setGroupId("com.maventwin.synthetic"); marker.setArtifactId("maventwin-marker-plugin"); marker.setVersion("1.0.0");
      PluginExecution execution = new PluginExecution(); execution.setId("maventwin-marker"); execution.setPhase("validate"); execution.addGoal("mark"); marker.addExecution(execution); build.addPlugin(marker);
    }
  }
}
